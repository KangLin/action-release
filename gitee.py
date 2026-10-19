#!/usr/bin/env python
# coding:utf-8

import os
import requests
import time
from requests_toolbelt import MultipartEncoder
from functools import wraps

retry_times = os.environ.get("gitee_upload_retry_times", "0")
try:
    retry_times = int(retry_times)
except Exception:
    retry_times = 0
    
def Retry(retry, include_exceptions = [Exception], exclude_exceptions = [ValueError], sleep = 1):
    def decoratedRetry(func):
        def checkRun(retry, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if no_catch(e, exclude_exceptions) or not need_catch(e, include_exceptions):
                    raise e
                if(retry == 0):
                    raise e
                else:
                    print('error catched:', e)
                    if sleep > 0:
                        time.sleep(sleep)
                    return checkRun(retry-1, *args, **kwargs)
                    
        @wraps(func)      
        def run(*args, **kwargs):
            return checkRun(retry, *args, **kwargs)
        return run
    return decoratedRetry

def need_catch(exception, include_exceptions):
    for ex in include_exceptions:
        if isinstance(exception, ex):
            return True
    return False
    
def no_catch(exception, exclude_exceptions):
    for ex in exclude_exceptions:
        if isinstance(exception, ex):
            return True
    return False
    
class Gitee:
    def __init__(self, owner, token):
        self.owner = owner
        self.token = token

    def create_release(self, repo, tag_name, name, body = '-', target_commitish = 'master'):
        url = f'https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases'
        data = {
            'access_token': self.token,
            'tag_name': tag_name,
            'name': name,
            'body': body,
            'target_commitish': target_commitish,
        }
        response = requests.post(url, data=data)
        res = response.json() 
        if response.status_code < 200 or response.status_code >= 300:
            return False, res["message"] if "message" in res else f"Response status_code is {response.status_code}"
        
        if "id" in res:
            return True, res["id"]
        else:
            return False, "No 'id' in response"

    @Retry(retry_times)
    def upload_asset(self, repo, release_id, files = None, file_name = None, file_path = None):
        if files:
            fields = [('access_token', self.token)]
            idx = 1
            file_handles = []  # Track file handles for proper cleanup
            try:
                for file_path in files:
                    file_path = file_path.strip()
                    if not os.path.isfile(file_path):
                        raise ValueError('file_path not exists: ' + file_path)
                    file_handle = open(file_path, 'rb')
                    file_handles.append(file_handle)
                    file = ('file', (os.path.basename(file_path), file_handle, 'application/octet-stream'))
                    idx = idx + 1
                    fields.append(file)
                
                m = MultipartEncoder(fields=fields)
                url = f"https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases/{release_id}/attach_files"
                response = requests.post(url, data=m, headers={'Content-Type': m.content_type})
            finally:
                # Close all file handles
                for handle in file_handles:
                    handle.close()
        elif file_name and file_path:
            with open(file_path, 'rb') as f:
                fields = {
                    'access_token': self.token,
                    'file': (file_name, f, 'application/octet-stream'),
                }
                m = MultipartEncoder(fields=fields)
                url = f"https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases/{release_id}/attach_files"
                response = requests.post(url, data=m, headers={'Content-Type': m.content_type})
        else:
            raise ValueError('files or (file_name and file_path) should not be False at the same time')
        
        # print(response.text)
        res = response.json()
        if response.status_code < 200 or response.status_code >= 300:
            return False, res["message"] if "message" in res else f"Response status_code is {response.status_code}"
        
        if "browser_download_url" in res:
            return True, res["browser_download_url"]
        else:
            return False, "No 'browser_download_url' in response"

    def get_release_by_tag(self, repo, tag_name):
        url = f'https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases/tags/{tag_name}'
        params = {'access_token': self.token}
        response = requests.get(url, params=params)
        res = response.json()
        if response.status_code != 200:
            return False, res.get("message", f"Status code {response.status_code}")
        if "id" in res:
            return True, res["id"]
        else:
            return False, "No release id found"

    def get_asset_id(self, repo, release_id, filename):
        url = f'https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases/{release_id}/attach_files'
        params = {'access_token': self.token, "per_page": 100}
        response = requests.get(url, params=params)
        res = response.json()
        if response.status_code != 200:
            return False, res.get("message", f"Status code {response.status_code}")
        for asset in res:
            if asset['name'] == filename:
                return True, asset['id']
        return False, "Asset not found"

    @Retry(retry_times)
    def update_asset(self, repo, tag_name, filename, new_file_path):
        success, release_id = self.get_release_by_tag(repo, tag_name)
        if not success:
            return False, release_id
        
        success, asset_id = self.get_asset_id(repo, release_id, filename)
        if not success:
            return False, asset_id
        
        success, msg = self.delete_asset(repo, release_id, asset_id)
        if not success:
            return False, msg
        
        return self.upload_asset(repo, release_id, file_name=filename, file_path=new_file_path)

    def delete_release_by_tag(self, repo, tag_name):
        success, release_id = self.get_release_by_tag(repo, tag_name)
        if not success:
            return False, release_id
        return self.delete_release(repo, release_id)

    def delete_release(self, repo, release_id):
        url = f'https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases/{release_id}'
        params = {'access_token': self.token}
        response = requests.delete(url, params=params)
        if response.status_code == 204:
            return True, "Release deleted successfully"
        else:
            res = response.json()
            return False, res.get("message", f"Status code {response.status_code}")

    def delete_asset_by_filename(self, repo, tag_name, filename):
        success, release_id = self.get_release_by_tag(repo, tag_name)
        if not success:
            return False, release_id
        
        success, asset_id = self.get_asset_id(repo, release_id, filename)
        if not success:
            return False, asset_id
        return self.delete_asset(repo, release_id, asset_id)

    def delete_asset(self, repo, release_id, asset_id):
        url = f'https://gitee.com/api/v5/repos/{self.owner}/{repo}/releases/{release_id}/attach_files/{asset_id}'
        params = {'access_token': self.token}
        response = requests.delete(url, params=params)
        if response.status_code == 204:
            return True, "Asset deleted successfully"
        else:
            res = response.json()
            return False, res.get("message", f"Status code {response.status_code}")


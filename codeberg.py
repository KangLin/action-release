#!/usr/bin/env python
# coding:utf-8

import os
import requests
import time
from requests_toolbelt import MultipartEncoder
from functools import wraps

API_BASE="https://codeberg.org/api/v1"

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

class Codeberg:
    def __init__(self, owner, token):
        self.owner = owner
        self.token = token
        if not self.owner or not self.token:
            raise ValueError(f"owner or token is empty: {owner}, {token}")

    def _auth_headers(self, extra=None):
        headers = {'Authorization': f'token {self.token}'}
        if extra:
            headers.update(extra)
        return headers

    # See: https://codeberg.org/api/swagger#/repository/repoCreateRelease
    def create_release(self, repo, tag_name, name, body = '-', target_commitish = 'master'):
        url = f'{API_BASE}/repos/{self.owner}/{repo}/releases'
        data = {
            'access_token': self.token,
            'tag_name': tag_name,
            'name': name,
            'body': body,
            'target_commitish': target_commitish,
        }
        response = requests.post(url, data=data, headers=self._auth_headers())
        res = response.json()
        if response.status_code != 201:
            return False, res["message"] if "message" in res else f"Response status_code is {response.status_code}"
        else:
            if "id" in res:
                return True, res["id"]
            else:
                return False, "No 'id' in response"

    # See: https://codeberg.org/api/swagger#/repository/repoCreateReleaseAttachment
    @Retry(retry_times)
    def upload_asset(self, repo, release_id, file_name, file_path):
        if not os.path.isfile(file_path):
            raise ValueError('file_path not exists: ' + file_path)

        with open(file_path, 'rb') as f:
            fields = {'attachment': (file_name, f, 'application/octet-stream')}
            m = MultipartEncoder(fields=fields)
            url = f"{API_BASE}/repos/{self.owner}/{repo}/releases/{release_id}/assets"
            response = requests.post(
                url,
                data=m,
                headers=self._auth_headers({'Content-Type': m.content_type}),
            )

        res = response.json()
        if response.status_code != 201:
            return False, res["message"] if "message" in res else f"Response status_code is {response.status_code}"
        else:
            if "browser_download_url" in res:
                return True, res["browser_download_url"]
            return False, "No 'browser_download_url' in response"

    # See: https://codeberg.org/api/swagger#/repository/repoGetReleaseByTag
    def get_release_by_tag(self, repo, tag_name):
        url = f'{API_BASE}/repos/{self.owner}/{repo}/releases/tags/{tag_name}'
        response = requests.get(url, headers=self._auth_headers())
        res = response.json()
        if response.status_code != 200:
            return False, res.get("message", f"Status code {response.status_code}")
        if "id" in res:
            return True, res["id"]
        else:
            return False, "No release id found"

    # See: https://codeberg.org/api/swagger#/repository/repoListReleaseAttachments
    def get_asset_id(self, repo, release_id, filename):
        url = f'{API_BASE}/repos/{self.owner}/{repo}/releases/{release_id}/assets'
        response = requests.get(url, headers=self._auth_headers({"per_page": 100}))
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

    # See: https://codeberg.org/api/swagger#/repository/repoDeleteRelease
    def delete_release(self, repo, release_id):
        url = f'{API_BASE}/repos/{self.owner}/{repo}/releases/{release_id}'
        response = requests.delete(url, headers=self._auth_headers())
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

    #See: https://codeberg.org/api/swagger#/repository/repoDeleteReleaseAttachment
    def delete_asset(self, repo, release_id, asset_id):
        url = f'{API_BASE}/repos/{self.owner}/{repo}/releases/{release_id}/assets/{asset_id}'
        response = requests.delete(url, headers=self._auth_headers())
        if response.status_code == 204:
            return True, "Asset deleted successfully"
        else:
            res = response.json()
            return False, res.get("message", f"Status code {response.status_code}")

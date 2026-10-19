#!/usr/bin/env python
# coding:utf-8

import os
import glob
from codeberg import Codeberg
from gitee import Gitee

def get(key):
    val = os.environ.get(key)
    if not val:
        raise ValueError(f'{key} not set in the environment')
    return val
    
def set_result(name, result):
    print("result: ", f"{name}={result}")
    github_out = os.environ.get("GITHUB_OUTPUT")
    if github_out:
        with open(github_out, 'a', encoding='utf-8') as output:
            if '\n' not in str(result):
                output.write(f"{name}={result}\n")
                print(f"{name}={result}\n")
            else:
                delimiter = 'EOF'
                output.write(f"{name}<<{delimiter}\n{result}\n{delimiter}\n")
                print(f"{name}<<{delimiter}\n{result}\n{delimiter}\n")
                
def upload_assets(release_files, release_client, release_repo, release_release_id):
    result = []
    uploaded_path = set()
    for file_path_pattern in release_files:
        file_path_pattern = file_path_pattern.strip()
        recursive = True if "**" in file_path_pattern else False
        files = glob.glob(file_path_pattern, recursive = recursive)
        if len(files) == 0:
            raise ValueError('file_path_pattern does not match: ' + file_path_pattern)
        for file_path in files:
            if file_path in uploaded_path or os.path.isdir(file_path):
                continue
            success, msg = release_client.upload_asset(release_repo, release_release_id, file_name = os.path.basename(file_path), file_path = file_path)
            if not success:
                raise Exception("Upload file asset failed: " + msg)
            result.append(msg)
            uploaded_path.add(file_path)
    return result

def create_release(release_client):
    release_repo = get('release_repo')
    release_tag_name = get('release_tag_name')
    release_release_name = get('release_release_name')
    release_release_body = get('release_release_body')
    release_target_commitish = get('release_target_commitish')
    
    release_files = os.environ.get('release_files')
    if release_files:
        release_files = release_files.strip().split("\n")
    else:
        release_file_name = os.environ.get('release_file_name')
        release_file_path = os.environ.get('release_file_path')
        if (release_file_name and not release_file_path) or (release_file_path and not release_file_name):
            raise ValueError('release_file_name and release_file_path should be set together')
        if release_file_path and not os.path.isfile(release_file_path):
            raise ValueError('release_file_path not exists: ' + release_file_path)

    success, release_id = release_client.create_release(repo = release_repo, tag_name = release_tag_name, name = release_release_name,
                body = release_release_body, target_commitish = release_target_commitish)
    if success:
        print(f"Release created successfully with ID: {release_id}")
        set_result("release-id", release_id)
        
        # Upload files if provided
        if release_files:
            result = upload_assets(release_files, release_client, release_repo, release_id)
            if result:
                set_result("download-url", '\n'.join(result))
        elif release_file_path:
            success, msg = release_client.upload_asset(release_repo, release_id, file_name = release_file_name, file_path = release_file_path)
            if not success:
                raise Exception("Upload file asset failed: " + msg)
            set_result("download-url", msg)
    else:
        raise Exception("Create release failed: " + str(release_id))

def upload_asset(release_client):
    release_repo = get('release_repo')
    release_files = os.environ.get('release_files')

    release_release_id = os.environ.get('release_release_id')
    if not release_release_id:
        release_tag_name = get('release_tag_name')
        success, release_release_id = release_client.get_release_by_tag(release_repo, release_tag_name)
        if not success:
            raise Exception(f"Failed to get release by tag {release_tag_name}")

    if release_files:
        release_files = release_files.strip().split("\n")
        result = upload_assets(release_files, release_client, release_repo, release_release_id)
        set_result("download-url", '\n'.join(result))
    else:
        release_file_name = get('release_file_name')
        release_file_path = get('release_file_path')
        if release_file_path and not os.path.isfile(release_file_path):
            raise ValueError('release_file_path not exists: ' + release_file_path)
        success, msg = release_client.upload_asset(release_repo, release_release_id, file_name = release_file_name, file_path = release_file_path)
        if not success:
            raise Exception("Upload file asset failed: " + msg)
        set_result("download-url", msg)

def delete_release(release_client):
    release_repo = get('release_repo')
    release_tag_name = get('release_tag_name')

    success, msg = release_client.delete_release_by_tag(release_repo, release_tag_name)
    if not success:
        raise Exception("Delete release failed: " + msg)
    print("Release deleted successfully")

def delete_asset(release_client):
    release_repo = get('release_repo')
    release_tag_name = get('release_tag_name')

    release_delete_assets = get('release_delete_assets')
    asset_names = [name.strip() for name in release_delete_assets.strip().split('\n') if name.strip()]

    for asset_name in asset_names:
        success, msg = release_client.delete_asset_by_filename(release_repo, release_tag_name, asset_name)
        if not success:
            raise Exception(f"Delete asset {asset_name} failed: " + msg)
        print(f"Asset {asset_name} deleted successfully")

def update_asset(release_client):
    release_repo = get('release_repo')
    release_tag_name = get('release_tag_name')
    release_old_asset_name = get('release_old_asset_name')
    release_new_file_path = get('release_new_file_path')
    
    if not os.path.isfile(release_new_file_path):
        raise ValueError('release_new_file_path not exists: ' + release_new_file_path)

    success, msg = release_client.update_asset(release_repo, release_tag_name, release_old_asset_name, release_new_file_path)
    if not success:
        raise Exception("Update asset failed: " + msg)
    print(f"Asset {release_old_asset_name} updated successfully")
    set_result("download-url", msg)

def get_release_client():
    home = get("release_home")
    owner = get('release_owner')
    token = get('release_token')
    match home:
        case "codeberg":
            return Codeberg(owner, token)
        case "gitee":
            return Gitee(owner, token)
        case _:
            raise ValueError(f"Unsupport hmoe: {home}")

if __name__ == "__main__":
    release_client = get_release_client()

    release_action = get("release_action")
    match release_action:
        case "create_release":
            create_release(release_client)
        case "upload_asset":
            upload_asset(release_client)
        case "delete_release":
            delete_release(release_client)
        case "delete_asset":
            delete_asset(release_client)
        case "update_asset":
            update_asset(release_client)
        case _:
            raise ValueError(f"Unknown action: {release_action}. Supported actions: create_release, upload_asset, delete_release, delete_asset, update_asset")

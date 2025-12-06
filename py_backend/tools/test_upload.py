#!/usr/bin/env python3
"""
Simple test script to POST a small file to the backend upload endpoint
and poll /admin/files to verify the upload and processing entries.

Usage:
  python3 tools/test_upload.py --file ./small_test.txt --sync

Note: remove this script after testing is complete as requested.
"""
import argparse
import time
import requests
import os

BACKEND = os.getenv('DW_BACKEND', 'http://127.0.0.1:11400')


def post_file(path, agent_id='demo', sync=False):
    url = f"{BACKEND}/api/upload"
    if sync:
        url += "?sync=true"
    files = {'file': open(path, 'rb')}
    data = {'agent_id': agent_id}
    print(f"Posting {path} to {url}...")
    r = requests.post(url, files=files, data=data)
    try:
        print('Response:', r.status_code, r.text)
    except Exception:
        print('Response received')
    return r


def poll_admin(agent_id='demo', attempts=10, delay=1.0):
    url = f"{BACKEND}/admin/files"
    for i in range(attempts):
        try:
            r = requests.get(url)
            if r.status_code == 200:
                data = r.json()
                agent_info = data.get('agents', {}).get(agent_id)
                print(f"[poll {i}] agent_info:", agent_info)
                return data
            else:
                print(f"Admin returned {r.status_code}")
        except Exception as e:
            print('Admin poll error:', e)
        time.sleep(delay)
    return None


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--file', '-f', required=True)
    p.add_argument('--agent', default='demo')
    p.add_argument('--sync', action='store_true')
    p.add_argument('--attempts', type=int, default=10)
    p.add_argument('--delay', type=float, default=1.0)
    args = p.parse_args()

    r = post_file(args.file, agent_id=args.agent, sync=args.sync)
    if r.status_code not in (200, 202):
        print('Upload may have failed; aborting poll.')
    else:
        print('Upload accepted; polling admin for status...')
        poll_admin(agent_id=args.agent, attempts=args.attempts, delay=args.delay)

    print('\nTest script finished. Remove this file when done.')

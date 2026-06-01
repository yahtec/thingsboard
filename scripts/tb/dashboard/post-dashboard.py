#!/usr/bin/env python3
"""
POST a dashboard JSON file to ThingsBoard via REST API.
Uses raw bytes to avoid encoding mojibake roundtrips (cf. PowerShell 5.1 issue).

Usage:
  post-dashboard.py <dashboard.json> <tb-host> <username> <password>
"""

import json
import sys
import urllib.request
import urllib.error

if len(sys.argv) != 5:
    sys.exit('Usage: post-dashboard.py <dashboard.json> <tb-host> <username> <password>')

path, host, user, pwd = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

# 1. Login
req = urllib.request.Request(
    f'{host}/api/auth/login',
    data=json.dumps({'username': user, 'password': pwd}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req) as r:
    token = json.loads(r.read().decode('utf-8'))['token']
print(f'Token len: {len(token)}')

# 2. Read dashboard JSON bytes (already proper UTF-8)
with open(path, 'rb') as f:
    body = f.read()
print(f'Dashboard JSON: {len(body)} bytes')

# 3. POST raw bytes
req = urllib.request.Request(
    f'{host}/api/dashboard',
    data=body,
    headers={
        'Content-Type': 'application/json; charset=utf-8',
        'X-Authorization': f'Bearer {token}',
    },
    method='POST',
)
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode('utf-8'))
    print(f'Posted OK. New version: {resp.get("version")}')
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8', errors='replace')
    print(f'HTTP {e.code}: {body[:500]}')
    sys.exit(1)

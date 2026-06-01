#!/usr/bin/env python3
"""
Restore a dashboard configuration from a backup file while keeping the current
version number (avoids 409 Conflict).

Usage:
  restore-config.py <recovered-backup.json> <dashboard-id> <tb-host> <username> <password>
"""

import json
import sys
import urllib.request
import urllib.error

if len(sys.argv) != 6:
    sys.exit('Usage: restore-config.py <recovered-backup.json> <dashboard-id> <tb-host> <username> <password>')

path, did, host, user, pwd = sys.argv[1:6]

# 1. Login
req = urllib.request.Request(
    f'{host}/api/auth/login',
    data=json.dumps({'username': user, 'password': pwd}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req) as r:
    token = json.loads(r.read().decode('utf-8'))['token']

# 2. Fetch current dashboard (with current version)
req = urllib.request.Request(
    f'{host}/api/dashboard/{did}',
    headers={'X-Authorization': f'Bearer {token}'},
)
with urllib.request.urlopen(req) as r:
    current = json.loads(r.read().decode('utf-8'))
print(f'Current version: {current["version"]}')

# 3. Load recovered backup
with open(path, 'rb') as f:
    backup = json.loads(f.read().decode('utf-8'))
print(f'Backup version: {backup["version"]} (will override with current)')

# 4. Use current dashboard meta + backup's configuration
restored = dict(current)
restored['configuration'] = backup['configuration']
# Keep current version, title, name, image, mobile_*, assignedCustomers as-is

# 5. POST
body = json.dumps(restored, ensure_ascii=False).encode('utf-8')
print(f'Body size: {len(body)} bytes')
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

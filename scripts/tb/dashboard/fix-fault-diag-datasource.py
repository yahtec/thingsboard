#!/usr/bin/env python3
"""
Le widget Fault Diagnostic (instance fa5e1c00-...) a un datasource avec dataKey
"id" qui peut etre ancien -> TB framework affiche "Aucune donnee a afficher
sur le widget" AVANT que le controllerScript ne prenne la main.

Fix : changer dataKey "id" -> "pac_v2" (ecrit chaque minute, donc toujours
frais), donc TB ne montre jamais son no-data message et le controllerScript
s'execute.
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
WIDGET_ID    = 'fa5e1c00-1234-1234-1234-fa017d106057'
BASE_URL     = 'https://thingsboard.tsmart.fr'


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o: return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o: return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()
    t = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    print(f'Dashboard v{dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/dashboard/backup/mes-installations.faultdiag-ds.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    fd = dash['configuration']['widgets'].get(WIDGET_ID)
    if not fd: sys.exit('Widget instance not found')
    ds_list = fd['config'].get('datasources', [])
    if not ds_list: sys.exit('No datasources')
    ds = ds_list[0]
    keys = ds.get('dataKeys', [])
    print(f'Current dataKeys: {[k.get("name") for k in keys]}')
    # Replace by single pac_v2 dataKey
    ds['dataKeys'] = [{
        'name': 'pac_v2',
        'type': 'timeseries',
        'color': '#2196f3',
        'label': 'pac_v2',
        'decimals': 0,
        'settings': {},
    }]
    print(f'New dataKeys: {[k["name"] for k in ds["dataKeys"]]}')

    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted v{resp["version"]}')


if __name__ == '__main__': main()

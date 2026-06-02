#!/usr/bin/env python3
"""
Normalise tous les layouts pour que le premier widget commence a row=0.
Apres le retrait du widget Navbar, il restait des gaps (widgets a row=1 ou 2).
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
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
    with open(f'scripts/tb/dashboard/backup/mes-installations.normalize-row.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    total_shifted = 0
    for sid, st in dash['configuration']['states'].items():
        for lt in ('main', 'mobile'):
            widgets = st.get('layouts', {}).get(lt, {}).get('widgets', {}) or {}
            if not widgets: continue
            min_row = min(lo.get('row', 0) for lo in widgets.values())
            if min_row > 0:
                for wid, lo in widgets.items():
                    lo['row'] = lo.get('row', 0) - min_row
                print(f'  {sid}/{lt}: shifted {len(widgets)} widgets by -{min_row} rows')
                total_shifted += len(widgets)

    if total_shifted == 0:
        print('Nothing to do (all layouts already start at row=0)')
        return
    resp = http_post('/api/dashboard', dash, t)
    print(f'\nPosted v{resp["version"]}')


if __name__ == '__main__': main()

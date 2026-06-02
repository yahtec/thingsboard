#!/usr/bin/env python3
"""
Retire le widget Navbar (a1b2c3d4...0010) des layouts de tous les states.
Les boutons sont maintenant dans la TB toolbar native (home.component.ts).
Le widget reste dans configuration.widgets pour rollback eventuel.

Shift les autres widgets de -2 rows (puisque Navbar sizeY=2 ne prend plus
de place).
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
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
    with open(f'scripts/tb/dashboard/backup/mes-installations.remove-navbar.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    removed = 0
    shifted = 0
    for sid, st in dash['configuration']['states'].items():
        for lt in ('main', 'mobile'):
            widgets = st.get('layouts', {}).get(lt, {}).get('widgets', {}) or {}
            if NAVBAR_ID in widgets:
                # Remember sizeY for shifting
                nav_sy = widgets[NAVBAR_ID].get('sizeY', 2)
                del widgets[NAVBAR_ID]
                removed += 1
                # Shift les autres widgets de -nav_sy rows
                for wid, lo in widgets.items():
                    r = lo.get('row', 0)
                    if r >= nav_sy:
                        lo['row'] = r - nav_sy
                        shifted += 1
                    if 'mobileOrder' in lo and lo['mobileOrder'] is not None:
                        lo['mobileOrder'] = max(0, lo['mobileOrder'] - 1)
                print(f'  state {sid}/{lt}: removed Navbar (was sizeY={nav_sy}), shifted {len(widgets)} widgets')

    if removed == 0:
        print('Nothing to do')
        return
    print(f'Total removed: {removed}, shifted: {shifted}')
    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted v{resp["version"]}')


if __name__ == '__main__': main()

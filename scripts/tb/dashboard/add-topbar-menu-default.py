#!/usr/bin/env python3
"""
Ajoute le widget Topbar (a1b2c3d4...0001) au layout des states 'menu' et
'default'. La Topbar sera placée en row=0, le Navbar existant est poussé
en row=1, les autres widgets décalés d'une ligne.

Idempotent : si Topbar deja dans le layout, skip.
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
TOPBAR_ID    = 'a1b2c3d4-0200-4000-a000-000000000001'
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


def patch_state(dash, state_id):
    """Insere Topbar en row=0 et decale les autres widgets de +1."""
    st = dash['configuration']['states'].get(state_id)
    if not st: return False, f'{state_id} not found'
    layout = st.get('layouts', {}).get('main', {})
    widgets = layout.get('widgets', {})
    if TOPBAR_ID in widgets:
        return False, f'Topbar already in {state_id}'
    # Decale tous les widgets existants de row+1
    for wid, lo in widgets.items():
        cur_row = lo.get('row', 0)
        lo['row'] = cur_row + 1
        # Mobile order : decale aussi
        if 'mobileOrder' in lo and lo['mobileOrder'] is not None:
            lo['mobileOrder'] = lo['mobileOrder'] + 1
    # Insert Topbar en row=0
    widgets[TOPBAR_ID] = {
        'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 1,
        'mobileOrder': 0, 'mobileHeight': 1,
    }
    return True, f'inserted Topbar row=0, shifted {len(widgets)-1} widgets +1'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()
    t = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    print(f'Dashboard v{dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/dashboard/backup/mes-installations.topbar-menu-default.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    any_changed = False
    for sid in ('menu', 'default'):
        c, msg = patch_state(dash, sid)
        print(f'  {sid:10}: {msg}')
        if c: any_changed = True
    if not any_changed:
        print('Nothing to do')
        return
    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted v{resp["version"]}')


if __name__ == '__main__': main()

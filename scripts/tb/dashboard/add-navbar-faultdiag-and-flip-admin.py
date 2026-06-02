#!/usr/bin/env python3
"""
1) Ajoute le widget Navbar (a1b2c3d4...0010) au state fault_diagnostic
   au-dessus du widget Diagnostic defaut. Boutons :
     - Defaut -> historique
     - Parametrage -> configuration (visible non-admin, cache admin)
2) Inverse la regle TBN-RESTRICT-ADMIN sur .back-btn[data-navtarget=configuration]
   Avant : cache par defaut, visible admin
   Apres : visible par defaut, cache admin (user normal voit Parametrages,
   admin ne le voit pas)

Idempotent (verifie presence avant ajout).

Usage:
  add-navbar-faultdiag-and-flip-admin.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
DIAG_WID     = 'fa5e1c00-1234-1234-1234-fa017d106057'
TOPBAR_ID    = 'a1b2c3d4-0200-4000-a000-000000000001'
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


def patch_layout_fault_diag(dash):
    st = dash['configuration']['states'].get('fault_diagnostic')
    if not st: return False, 'fault_diagnostic state not found'
    layout = st.get('layouts', {}).get('main', {})
    widgets = layout.get('widgets', {})
    if NAVBAR_ID in widgets:
        return False, 'Navbar already in fault_diagnostic'
    # Insertion sous topbar (row=0, sizeY=1) -> Navbar row=1 sizeY=1
    # Decaler Diagnostic defaut row 1 -> row 2
    widgets[NAVBAR_ID] = {
        'col': 0, 'row': 1, 'sizeX': 24, 'sizeY': 1,
        'mobileOrder': 1, 'mobileHeight': 1,
    }
    if DIAG_WID in widgets:
        widgets[DIAG_WID]['row'] = 2
        widgets[DIAG_WID]['mobileOrder'] = 2
    return True, 'Navbar inserted at row=1, Diag pushed to row=2'


def patch_navbar_admin_flip(dash):
    """Inverse TBN-RESTRICT-ADMIN dans le CSS du Navbar."""
    nv = dash['configuration']['widgets'].get(NAVBAR_ID)
    if not nv: return False, 'Navbar widget not found'
    css = nv['config']['settings'].get('cardCss', '')
    OLD = '.md-nav .back-btn[data-navtarget="configuration"] { display:none; }\n.md-nav.tbn-is-admin .back-btn[data-navtarget="configuration"] { display:inline-flex; }'
    NEW = '.md-nav .back-btn[data-navtarget="configuration"] { display:inline-flex; }\n.md-nav.tbn-is-admin .back-btn[data-navtarget="configuration"] { display:none; }'
    if NEW in css:
        return False, 'admin flip already applied (idempotent)'
    if OLD not in css:
        # Try whitespace-flexible match
        import re
        pattern = re.compile(r'\.md-nav\s+\.back-btn\[data-navtarget="configuration"\]\s*\{\s*display:\s*none;?\s*\}\s*\.md-nav\.tbn-is-admin\s+\.back-btn\[data-navtarget="configuration"\]\s*\{\s*display:\s*inline-flex;?\s*\}', re.DOTALL)
        m = pattern.search(css)
        if not m: return False, f'TBN-RESTRICT-ADMIN block pattern not found (CSS may have changed)'
        new_css = css[:m.start()] + NEW + css[m.end():]
    else:
        new_css = css.replace(OLD, NEW, 1)
    nv['config']['settings']['cardCss'] = new_css
    return True, 'inverted: configuration visible by default, hidden for admin'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Dashboard version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.faultdiag-nav.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    lc, lmsg = patch_layout_fault_diag(dash)
    print(f'  Layout fault_diag : {lmsg}')
    fc, fmsg = patch_navbar_admin_flip(dash)
    print(f'  Admin flip Navbar : {fmsg}')

    if not lc and not fc:
        print('Nothing to change -- exit')
        return

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

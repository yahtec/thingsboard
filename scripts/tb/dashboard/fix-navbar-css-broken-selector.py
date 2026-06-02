#!/usr/bin/env python3
"""
Fix bug CSS Navbar : un de mes scripts plus tot (fix-navbar-buttons.py) a
strippe `.md-nav .nav-btns { display:none; }` qui faisait partie d'un
selector group multi-ligne. Resultat : la regle est CASSEE et le selector
group .md-nav .md-nav-crumb-sep, .md-nav .md-nav-residence,
.md-nav .md-nav-laststamp,  (virgule + retour ligne + .md-nav.md-nav-detail-mode...)
n'a plus de declaration. Le browser ignore la regle entiere -> separateur
et residence visibles par defaut sur menu.

Fix : remplace le bloc casse par des regles separees explicites.
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
BASE_URL     = 'https://thingsboard.tsmart.fr'

OLD_BLOCK = """/* Hide detail-only chrome by default; revealed only when an entityId is in URL */
.md-nav .md-nav-crumb-sep,
.md-nav .md-nav-residence,
.md-nav .md-nav-laststamp,

.md-nav.md-nav-detail-mode .md-nav-crumb-sep,
.md-nav.md-nav-detail-mode .md-nav-residence { display:inline; }
.md-nav.md-nav-detail-mode .md-nav-laststamp { display:block; }

.md-nav:not(.md-nav-detail-mode) .md-nav-crumb-link { cursor:default; }"""

NEW_BLOCK = """/* Hide detail-only chrome by default; revealed only when an entityId is in URL */
.md-nav .md-nav-crumb-sep { display:none; }
.md-nav .md-nav-residence { display:none; }
.md-nav .md-nav-laststamp { display:none; }
.md-nav.md-nav-detail-mode .md-nav-crumb-sep { display:inline; }
.md-nav.md-nav-detail-mode .md-nav-residence { display:inline; }
.md-nav.md-nav-detail-mode .md-nav-laststamp { display:block; }
.md-nav:not(.md-nav-detail-mode) .md-nav-crumb-link { cursor:default; }"""


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
    with open(f'scripts/tb/dashboard/backup/mes-installations.css-broken-fix.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    nv = dash['configuration']['widgets'][NAVBAR_ID]
    css = nv['config']['settings'].get('cardCss','')
    if NEW_BLOCK in css:
        print('  CSS already fixed (idempotent)')
        return
    if OLD_BLOCK not in css:
        sys.exit('OLD_BLOCK pattern not found in CSS (CSS may have changed)')
    nv['config']['settings']['cardCss'] = css.replace(OLD_BLOCK, NEW_BLOCK, 1)
    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted v{resp["version"]}')


if __name__ == '__main__': main()

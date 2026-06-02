#!/usr/bin/env python3
"""
Retire les regles CSS qui cachent les boutons Defaut/Parametrage du Navbar.
Le current dashboard avait :
    .md-nav .nav-btns { display:none; }
    .md-nav.md-nav-detail-mode .nav-btns { display:flex; }
Et un inline <script> qui ajoute md-nav-detail-mode si entityId. Mais TB
peut sanitize les scripts dans html_card => boutons jamais visibles.
Fix : retirer les regles (comme unite_backup) => boutons toujours visibles.

Idempotent (verifie presence de la regle avant retirer).

Usage:
  fix-navbar-buttons.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error, re

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
BASE_URL     = 'https://thingsboard.tsmart.fr'

RULES_TO_STRIP = [
    r'\.md-nav\s+\.nav-btns\s*\{\s*display:\s*none;?\s*\}',
    r'\.md-nav\.md-nav-detail-mode\s+\.nav-btns\s*\{\s*display:\s*flex;?\s*\}',
]


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

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.navfix.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    nv = dash['configuration']['widgets'].get(NAVBAR_ID)
    if not nv: sys.exit('Navbar widget not found')
    css = nv['config']['settings'].get('cardCss', '')
    new_css = css
    removed = 0
    for pattern in RULES_TO_STRIP:
        new_css, n = re.subn(pattern, '', new_css)
        removed += n
    if removed == 0:
        print('  No matching rules to strip (already fixed or different format)')
        return
    nv['config']['settings']['cardCss'] = new_css
    print(f'  Stripped {removed} CSS rule(s) hiding nav-btns. Buttons now always visible.')
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

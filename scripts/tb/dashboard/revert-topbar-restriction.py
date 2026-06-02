#!/usr/bin/env python3
"""
Revert de la restriction Topbar uniquement-donnees_HP1 introduite par
conditional-bars-visibility.py.

Le user veut la Topbar (Accueil/Profil/Compte/Deco) visible sur TOUS les
states ou elle est layout-placee : historique, fault_diagnostic,
configuration, donnees_HP1, profil, notifications_admin.

Le mecanisme TBN-RESTRICT-ADMIN existant gere deja la visibilite du
bouton Comptes (TENANT_ADMIN OR is_admin=true).

Cette modif ne touche PAS au Navbar (la restriction menu vs default
reste en place via __CONDITIONAL_BARS_NAV__).

Idempotent : retire les marqueurs __CONDITIONAL_BARS_TOPBAR__.

Usage:
  revert-topbar-restriction.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error, re

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
TOPBAR_ID    = 'a1b2c3d4-0200-4000-a000-000000000001'
BASE_URL     = 'https://thingsboard.tsmart.fr'
MARKER       = '__CONDITIONAL_BARS_TOPBAR__'


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


def strip_block(text, marker):
    """Retire bloc CSS comment + regle + scriptbloc contenant marker."""
    # Retire CSS comment + lignes jusqu'a fin du bloc (delimite par 2 newlines ou /* fin */)
    # Approche : split sur le marker et reconstitue
    # Pattern attendu pour CSS : /* __MARKER__ : description */\n  rule { ... }\n  rule { ... }
    # Pattern pour HTML : <script>/* __MARKER__ ... */\n  ...\n</script>
    out = text
    # CSS bloc : comment + regles consecutives  (greedy until next /* or end)
    css_pattern = r'\n?/\*\s*' + re.escape(marker) + r'.*?\n(?:[^/]*\n)*'
    out = re.sub(css_pattern, '\n', out, flags=re.DOTALL)
    # JS bloc : <script>/* MARKER ... </script>
    js_pattern = r'\n?<script>/\*\s*' + re.escape(marker) + r'.*?</script>\n?'
    out = re.sub(js_pattern, '\n', out, flags=re.DOTALL)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Dashboard version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.topbar-revert.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    tb = dash['configuration']['widgets'].get(TOPBAR_ID)
    if not tb: sys.exit('Topbar widget not found')
    settings = tb['config']['settings']
    css_before = settings.get('cardCss', '')
    html_before = settings.get('cardHtml', '')
    if MARKER not in css_before and MARKER not in html_before:
        print(f'  Topbar already reverted (no {MARKER} found)')
        return
    settings['cardCss']  = strip_block(css_before,  MARKER)
    settings['cardHtml'] = strip_block(html_before, MARKER)
    print(f'  CSS: {len(css_before)} -> {len(settings["cardCss"])} chars')
    print(f'  HTML: {len(html_before)} -> {len(settings["cardHtml"])} chars')
    # Sanity check no residual marker
    if MARKER in settings['cardCss'] or MARKER in settings['cardHtml']:
        print(f'  WARN: marker still present after strip!')
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

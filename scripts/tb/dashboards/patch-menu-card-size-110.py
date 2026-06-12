#!/usr/bin/env python3
"""
Agrandit de 10% les cards chaufferies de la page menu (liste du parc).

Widget HTML Value Card 77e3ece4 du dashboard Mes Installations, settings.cardCss :
  - .chaufferie-card  width 200px -> 220px
  - .card-photo       height 130px -> 143px
Les tailles de police et la variante mobile (260px) sont inchangees.

Idempotent : marker __MENU_CARD_SIZE_110_V1__ dans le cardCss.

Usage:
  patch-menu-card-size-110.py --pwd <pwd> [--dry-run]
  TB_TOKEN=... patch-menu-card-size-110.py [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
WID_MENU     = '77e3ece4-32d7-80d8-22b5-a0ff8a74caff'
MARKER       = '__MENU_CARD_SIZE_110_V1__'

OLD_WIDTH  = 'width: 200px;'
NEW_WIDTH  = 'width: 220px; /* ' + MARKER + ' +10% */'
OLD_PHOTO  = 'height: 130px;'
NEW_PHOTO  = 'height: 143px;'


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}',
        headers={'X-Authorization': f'Bearer {t}'}, method='GET')
    try:
        with urllib.request.urlopen(r, timeout=60) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'GET {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def must_replace(s, old, new, label, count=1):
    n = s.count(old)
    if n != count:
        sys.exit(f'[{label}] anchor trouve {n} fois (attendu {count}) : {old[:80]!r}')
    return s.replace(old, new, count)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = os.environ.get('TB_TOKEN')
    if not t:
        if not args.pwd:
            sys.exit('Fournir --pwd ou definir TB_TOKEN')
        t = login(args.user, args.pwd)

    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    widgets = dash['configuration']['widgets']
    if WID_MENU not in widgets:
        sys.exit(f'widget menu absent : {WID_MENU}')
    settings = widgets[WID_MENU]['config']['settings']
    css = settings.get('cardCss', '')
    print(f'dashboard v{dash.get("version","?")}, cardCss {len(css)} chars')

    if MARKER in css:
        print('  Already patched (idempotent skip)')
        return

    new_css = must_replace(css, OLD_WIDTH, NEW_WIDTH, 'card-width')
    new_css = must_replace(new_css, OLD_PHOTO, NEW_PHOTO, 'photo-height')

    if args.dry_run:
        print(f'DRY-RUN: cardCss {len(css)} -> {len(new_css)} chars. No POST.')
        return

    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'backup-mes-installations.before_card_size.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    settings['cardCss'] = new_css
    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted OK. Dashboard version: {resp.get("version","?")}')


if __name__ == '__main__':
    main()

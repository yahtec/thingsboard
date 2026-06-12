#!/usr/bin/env python3
"""
Regle la taille des cards chaufferies de la page menu (liste du parc).

Widget HTML Value Card 77e3ece4 du dashboard Mes Installations, settings.cardCss :
  - .chaufferie-card  width  -> --width px
  - .card-photo       height -> round(width * 0.65) px (ratio d'origine 130/200)
La variante mobile (260px) et les polices sont inchangees.

Idempotent par nature : si la taille demandee est deja en place, no-op.
Historique : 200px (origine) -> 220 (v322) -> 240 (v323) -> parametrable.

Usage:
  set-menu-card-size.py --width 264 --pwd <pwd> [--dry-run]
  TB_TOKEN=... set-menu-card-size.py --width 264 [--dry-run]
"""

import argparse, json, os, re, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
WID_MENU     = '77e3ece4-32d7-80d8-22b5-a0ff8a74caff'
PHOTO_RATIO  = 0.65  # 130/200 d'origine


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


def set_prop_in_block(css, selector, prop, value, label):
    """Remplace `prop: <n>px;` (+ commentaire eventuel sur la meme ligne)
    dans le premier bloc `selector { ... }`. Retourne (css, old_value)."""
    m = re.search(re.escape(selector) + r'\s*\{[^}]*\}', css)
    if not m:
        sys.exit(f'[{label}] bloc {selector!r} introuvable')
    block = m.group(0)
    pm = re.search(re.escape(prop) + r':\s*(\d+)px;(?:[ \t]*/\*[^*]*\*/)?', block)
    if not pm:
        sys.exit(f'[{label}] propriete {prop!r} introuvable dans {selector!r}')
    old = int(pm.group(1))
    new_block = block[:pm.start()] + f'{prop}: {value}px;' + block[pm.end():]
    return css[:m.start()] + new_block + css[m.end():], old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--width', type=int, required=True, help='largeur card en px')
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    photo_h = round(args.width * PHOTO_RATIO)

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

    new_css, old_w = set_prop_in_block(css, '.chaufferie-card', 'width', args.width, 'card-width')
    new_css, old_h = set_prop_in_block(new_css, '.card-photo', 'height', photo_h, 'photo-height')
    print(f'  width  {old_w} -> {args.width}px')
    print(f'  photo  {old_h} -> {photo_h}px')

    if old_w == args.width and old_h == photo_h:
        print('  Deja a la taille demandee (no-op)')
        return
    if args.dry_run:
        print('DRY-RUN: no POST.')
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

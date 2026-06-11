#!/usr/bin/env python3
"""
State 'donnees_HP1' — reduit la hauteur des 6 timelines PAC/chaudiere
(sizeY 8 -> 6.5) et remonte les widgets en dessous en consequence.

Nouvelle grille verticale :
  PAC info 0..7, timeline 7..8.5,
  PAC charts rows 8.5 et 15 (sizeY 6.5),
  Chaudiere info 21.5 (sizeY 6),
  Chaudiere charts 27.5 (sizeY 6.5),
  pie 34.

Idempotent : skip si le chart Pressions est deja en sizeY 6.5.

Usage:
  shrink-pac-charts-height.py --pwd <pwd> [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'donnees_HP1'

WID_PRESS      = 'a1b2c3d4-0601-4000-a000-000000000001'
WID_TEMP       = 'a1b2c3d4-0001-4000-a000-000000000001'
WID_FRIG       = 'a1b2c3d4-0602-4000-a000-000000000002'
WID_COMP       = 'a1b2c3d4-0603-4000-a000-000000000003'
WID_BOIL_INFO  = 'a1b2c3d4-0002-4000-a000-000000000002'
WID_BOIL_CHART = 'a1b2c3d4-0003-4000-a000-000000000003'
WID_BOIL2      = 'a1b2c3d4-0604-4000-a000-000000000004'
WID_PIE        = 'a1b2c3d4-9997-4000-a000-000000000097'

CHART_SY = 6.5
MOVES = {
    WID_PRESS:      {'row': 8.5,  'sizeY': CHART_SY},
    WID_TEMP:       {'row': 8.5,  'sizeY': CHART_SY},
    WID_FRIG:       {'row': 15,   'sizeY': CHART_SY},
    WID_COMP:       {'row': 15,   'sizeY': CHART_SY},
    WID_BOIL_INFO:  {'row': 21.5},
    WID_BOIL_CHART: {'row': 27.5, 'sizeY': CHART_SY},
    WID_BOIL2:      {'row': 27.5, 'sizeY': CHART_SY},
    WID_PIE:        {'row': 34},
}


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
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
    lay = dash['configuration']['states'][STATE_ID]['layouts']['main']['widgets']

    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(here, f'backup-mes-installations.before_chart_shrink.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    if lay[WID_PRESS]['sizeY'] == CHART_SY:
        sys.exit('Deja applique. Rien a faire.')

    for wid, vals in MOVES.items():
        if wid not in lay:
            sys.exit(f'Widget {wid} absent du layout — etat inattendu')
        lay[wid].update(vals)
        print(f"  [{wid[:13]}...] -> {vals}")

    if args.dry_run:
        prev = bak.replace('.before_chart_shrink.', '.preview_chart_shrink.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

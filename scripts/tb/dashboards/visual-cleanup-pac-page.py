#!/usr/bin/env python3
"""
State 'donnees_HP1' — nettoyage visuel (feedback user 2026-06-11) :

1. Supprime le plafond max-height:420px de .chart-container sur les 6
   charts : les courbes remplissent toute la cellule, plus de bande vide.
3. Chaudiere Info sizeY 6 -> 4.5, rangées suivantes remontées
   (charts chaudiere 27.5 -> 26, pie 34 -> 32.5).
4. Camembert sizeY 8 -> 5.5.
5. Titre 'Courbes Chaudière (24 heures)' -> 'Températures chaudière'.

Idempotent : skip si max-height deja absent du chart Pressions.

Usage:
  visual-cleanup-pac-page.py --pwd <pwd> [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'donnees_HP1'

CHART_WIDS = [
    'a1b2c3d4-0601-4000-a000-000000000001',  # Pressions
    'a1b2c3d4-0001-4000-a000-000000000001',  # Temperatures
    'a1b2c3d4-0602-4000-a000-000000000002',  # Frigo
    'a1b2c3d4-0603-4000-a000-000000000003',  # Compresseur
    'a1b2c3d4-0003-4000-a000-000000000003',  # Chaudiere temperatures
    'a1b2c3d4-0604-4000-a000-000000000004',  # Bruleur / circuit eau
]
WID_BOIL_INFO  = 'a1b2c3d4-0002-4000-a000-000000000002'
WID_BOIL_CHART = 'a1b2c3d4-0003-4000-a000-000000000003'
WID_BOIL2      = 'a1b2c3d4-0604-4000-a000-000000000004'
WID_PIE        = 'a1b2c3d4-9997-4000-a000-000000000097'

CSS_OLD = '    flex: 1 1 auto; min-height: 160px; max-height: 420px;'
CSS_NEW = '    flex: 1 1 auto; min-height: 160px;'

TITLE_OLD = 'Courbes Chaudière (24 heures)'
TITLE_NEW = 'Températures chaudière'


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
    conf = dash['configuration']
    lay = conf['states'][STATE_ID]['layouts']['main']['widgets']

    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(here, f'backup-mes-installations.before_visual_cleanup.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    if CSS_OLD not in conf['widgets'][CHART_WIDS[0]]['config']['settings']['markdownCss']:
        sys.exit('Deja applique (max-height absent). Rien a faire.')

    # 1. plafond max-height supprime sur les 6 charts
    for wid in CHART_WIDS:
        s = conf['widgets'][wid]['config']['settings']
        if CSS_OLD not in s['markdownCss']:
            sys.exit(f'  [css] anchor introuvable sur {wid} — etat inattendu')
        s['markdownCss'] = s['markdownCss'].replace(CSS_OLD, CSS_NEW, 1)
    print('  [css] max-height 420px supprime sur les 6 charts')

    # 5. titre chart temperatures chaudiere
    w = conf['widgets'][WID_BOIL_CHART]
    fn = w['config']['settings']['markdownTextFunction']
    if TITLE_OLD not in fn:
        sys.exit(f'  [titre] "{TITLE_OLD}" introuvable')
    w['config']['settings']['markdownTextFunction'] = fn.replace(TITLE_OLD, TITLE_NEW, 1)
    print(f'  [titre] "{TITLE_OLD}" -> "{TITLE_NEW}"')

    # 3 + 4. layout
    lay[WID_BOIL_INFO]['sizeY'] = 4.5
    lay[WID_BOIL_CHART]['row'] = 26
    lay[WID_BOIL2]['row'] = 26
    lay[WID_PIE].update({'row': 32.5, 'sizeY': 5.5})
    print('  [layout] info chaud sizeY 4.5, charts chaud row 26, pie row 32.5 sizeY 5.5')

    if args.dry_run:
        prev = bak.replace('.before_visual_cleanup.', '.preview_visual_cleanup.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

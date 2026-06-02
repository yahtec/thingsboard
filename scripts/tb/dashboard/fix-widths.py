#!/usr/bin/env python3
"""
Largeur uniforme des 7 widgets row 7 + masquage CSS des PAC absents.

- Tous widgets actifs : sizeX = 3 cols (largeur max ~125 px)
- Layout : DG | PAC1 | PAC2 | PAC3 | PAC4 | Chauffage | ECS, col 0..20, total 21 cols
- CSS injectee dans customCss :
    gridster-item:has(.pac-absent-host) { display: none !important; }
  -> les cellules contenant le marker hidden disparaissent visuellement.
  Note : gridster2 ne reflowe pas auto en l'absence d'un item ; les widgets
  conservent leurs positions absolues. Les cellules absentes laisseront donc
  un trou. Si le user veut un collapse strict, il faudra une refonte (1 widget
  unique qui gere son layout interne via flexbox).

Usage:
  fix-widths.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'

WIDGETS_ROW7 = [
    ('a1b2c3d4-d600-4000-a000-000000000001', 0),   # DG
    ('a1b2c3d4-d600-4000-a000-000000000101', 3),   # PAC HP1
    ('a1b2c3d4-d600-4000-a000-000000000102', 6),   # PAC HP2
    ('a1b2c3d4-d600-4000-a000-000000000103', 9),   # PAC HP3
    ('a1b2c3d4-d600-4000-a000-000000000104', 12),  # PAC HP4
    ('a1b2c3d4-d600-4000-a000-000000000202', 15),  # Chauffage
    ('a1b2c3d4-d600-4000-a000-000000000201', 18),  # ECS
]
SIZE_X = 3

# CSS marker pour cacher les gridster-item contenant .pac-absent-host
HIDE_CSS_MARKER = '/* === pac-absent-hide === */'
HIDE_CSS = f'''
{HIDE_CSS_MARKER}
gridster-item:has(.pac-absent-host),
.gridster-item:has(.pac-absent-host),
[class*="gridster-item"]:has(.pac-absent-host) {{
  display: none !important;
  width: 0 !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}}
'''


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
    backup = f'scripts/tb/dashboard/backup/mes-installations.widths.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup}')

    widgets = dash['configuration']['widgets']
    lyt = dash['configuration']['states']['default']['layouts']['main']['widgets']

    for wid, col in WIDGETS_ROW7:
        if wid not in lyt: continue
        old = (lyt[wid].get('col'), lyt[wid].get('sizeX'))
        lyt[wid]['col'] = col
        lyt[wid]['sizeX'] = SIZE_X
        if wid in widgets:
            widgets[wid]['col'] = col
            widgets[wid]['sizeX'] = SIZE_X
        title = widgets.get(wid, {}).get('config', {}).get('title', '?')
        print(f'  [{title:25s}] col {old[0]} -> {col}, sizeX {old[1]} -> {SIZE_X}')

    # Inject CSS for hiding absent gridster-item
    settings = dash['configuration'].setdefault('settings', {})
    css = settings.get('customCss', '')
    if HIDE_CSS_MARKER not in css:
        settings['customCss'] = css + '\n' + HIDE_CSS
        print('  injected pac-absent-hide CSS into customCss')
    else:
        print('  pac-absent-hide CSS already present')

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Ajuste hauteurs widgets sur l'etat default :
- gridSettings.autoFillHeight: False (page scrolle, pas de compression)
- Photo + Map sizeY=5 (350 px), mobileHeight restaure original
- 7 widgets row 7 sizeY=6 (420 px), mobileHeight=6 par defaut (5 pour ECS/Chauffage)

Usage:
  fix-height-mobile.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'

# Par-widget : (sizeY, mobileHeight)
WIDGET_HEIGHTS = {
    # photo + map -- restore originals
    'be5e1a3a-74e5-7f97-d422-4030e48fcf95': (5, 5),    # HTML Value Card photo
    '1a5b4c03-ba38-ad06-5f7a-b82453a7807d': (5, 7),    # Map
    # row 12 widgets -- desktop 6 rows = 420 px, mobile restore originals
    'a1b2c3d4-d600-4000-a000-000000000001': (6, 6),    # DG
    'a1b2c3d4-d600-4000-a000-000000000101': (6, 6),    # PAC HP1
    'a1b2c3d4-d600-4000-a000-000000000102': (6, 6),    # PAC HP2
    'a1b2c3d4-d600-4000-a000-000000000103': (6, 6),    # PAC HP3
    'a1b2c3d4-d600-4000-a000-000000000104': (6, 6),    # PAC HP4
    'a1b2c3d4-d600-4000-a000-000000000202': (6, 5),    # Chauffage
    'a1b2c3d4-d600-4000-a000-000000000201': (6, 5),    # ECS
}


def http_get(path, token):
    req = urllib.request.Request(f'{BASE_URL}{path}', headers={'X-Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))

def http_post(path, body_obj, token):
    body = json.dumps(body_obj, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f'{BASE_URL}{path}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {token}'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def login(user, pwd):
    body = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    req = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.height.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup}')

    main_layout = dash['configuration']['states']['default']['layouts']['main']
    grid = main_layout.get('gridSettings', {})
    grid['autoFillHeight'] = False
    main_layout['gridSettings'] = grid

    widgets = dash['configuration']['widgets']
    lyt = main_layout['widgets']
    for wid, (sy, mh) in WIDGET_HEIGHTS.items():
        if wid not in lyt: continue
        old_sy, old_mh = lyt[wid].get('sizeY'), lyt[wid].get('mobileHeight')
        lyt[wid]['sizeY'] = sy
        lyt[wid]['mobileHeight'] = mh
        if wid in widgets:
            widgets[wid]['sizeY'] = sy
        title = widgets.get(wid, {}).get('config', {}).get('title', '?')
        print(f'  [{title:25s}] sizeY {old_sy} -> {sy}, mobileHeight {old_mh} -> {mh}')

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

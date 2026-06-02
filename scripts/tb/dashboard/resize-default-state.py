#!/usr/bin/env python3
"""
Redimensionne photo + map sur l'etat default du dashboard "Mes Installations".

Avant : photo 5x5, map 17x5 sur row 2.  Widgets PAC/ECS/Chauffage sur rows 7-10.
Apres : photo 10x10, map 14x10 sur row 2 (meme hauteur).  Widgets PAC/ECS/Chauffage
        decales de +5 rows pour s'enchainer apres la nouvelle hauteur.

Usage:
  resize-default-state.py --pwd <pwd> [--dry-run]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'

# Layout updates : widget_id -> new layout
LAYOUT_UPDATES = {
    # Resize photo + map (row 2, hauteur 10 au lieu de 5)
    'be5e1a3a-74e5-7f97-d422-4030e48fcf95': {'col': 0,  'row': 2, 'sizeX': 10, 'sizeY': 10},   # HTML Value Card (photo)
    '1a5b4c03-ba38-ad06-5f7a-b82453a7807d': {'col': 10, 'row': 2, 'sizeX': 14, 'sizeY': 10},   # Map
    # Shift widgets a partir de row 7 vers row 12 (+5 rows)
    'a1b2c3d4-d600-4000-a000-000000000001': {'col': 0,  'row': 12, 'sizeX': 4,  'sizeY': 3},   # Donnees generales
    'a1b2c3d4-d600-4000-a000-000000000101': {'col': 4,  'row': 12, 'sizeX': 5,  'sizeY': 3},   # PAC HP1
    'a1b2c3d4-d600-4000-a000-000000000102': {'col': 9,  'row': 12, 'sizeX': 5,  'sizeY': 3},   # PAC HP2
    'a1b2c3d4-d600-4000-a000-000000000103': {'col': 14, 'row': 12, 'sizeX': 5,  'sizeY': 3},   # PAC HP3
    'a1b2c3d4-d600-4000-a000-000000000104': {'col': 19, 'row': 12, 'sizeX': 5,  'sizeY': 3},   # PAC HP4
    # Shift widgets a partir de row 10 vers row 15
    'a1b2c3d4-d600-4000-a000-000000000201': {'col': 0,  'row': 15, 'sizeX': 12, 'sizeY': 3},   # ECS
    'a1b2c3d4-d600-4000-a000-000000000202': {'col': 12, 'row': 15, 'sizeX': 12, 'sizeY': 3},   # Chauffage
}


def http_get(path, token):
    req = urllib.request.Request(f'{BASE_URL}{path}', headers={'X-Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def http_post(path, body_obj, token):
    body = json.dumps(body_obj, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE_URL}{path}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {token}'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        sys.exit(f'HTTP {e.code}: {body[:500]}')


def login(user, pwd):
    body = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE_URL}/api/auth/login', data=body,
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    print('=== Step 1: Login + fetch ===')
    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup_path = f'scripts/tb/dashboard/backup/mes-installations.resize.{ts}.json'
    with open(backup_path, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup_path}')

    print('\n=== Step 2: Apply layout updates ===')
    widgets = dash['configuration']['widgets']
    lyt = dash['configuration']['states']['default']['layouts']['main']['widgets']
    for wid, new_lyt in LAYOUT_UPDATES.items():
        if wid not in lyt:
            print(f'  SKIP {wid} (not in default state)')
            continue
        old = dict(lyt[wid])
        lyt[wid].update(new_lyt)
        # Also update widget def sizes (defensive)
        if wid in widgets:
            widgets[wid].update({
                'col': new_lyt['col'], 'row': new_lyt['row'],
                'sizeX': new_lyt['sizeX'], 'sizeY': new_lyt['sizeY'],
            })
        title = widgets.get(wid, {}).get('config', {}).get('title', '?')
        print(f'  [{title:25s}]  {old.get("col"):>2},{old.get("row"):>2}  {old.get("sizeX")}x{old.get("sizeY"):<3}'
              f'  ->  {new_lyt["col"]:>2},{new_lyt["row"]:>2}  {new_lyt["sizeX"]}x{new_lyt["sizeY"]}')

    print('\n=== Step 3: POST ===')
    if args.dry_run:
        preview = f'scripts/tb/dashboard/backup/mes-installations.resize.preview.{ts}.json'
        with open(preview, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'DRY-RUN. Preview: {preview}')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

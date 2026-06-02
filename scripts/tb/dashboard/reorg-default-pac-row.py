#!/usr/bin/env python3
"""
Reorganise l'etat default :
- Donnees generales + 4 PAC HP + Chauffage + ECS sur UNE seule ligne (row 12)
- Ordre G->D : DG | PAC1 | PAC2 | PAC3 | PAC4 | Chauffage | ECS
- Largeurs : DG 4 + 4xPAC 3 + Chauffage 4 + ECS 4 = 24 cols ✓
- Hauteur : 8 rows (560 px) pour eviter le scroll interne

PAC HP{N} absent (comm != true) -> rend <div style="display:none"> (cellule
reste 4 cols mais blanche). Marker __PACV2_HIDE_ABSENT__ pour idempotence.

Usage:
  reorg-default-pac-row.py --pwd <pwd> [--dry-run]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
HIDE_MARKER  = '__PACV2_HIDE_ABSENT__'

# Layout target (row 12, sizeY 8 partout)
# Ordre G->D : DG | PAC1..4 | Chauffage | ECS  (chauffage AVANT ECS)
LAYOUT_UPDATES = {
    'a1b2c3d4-d600-4000-a000-000000000001': {'col': 0,  'row': 12, 'sizeX': 4, 'sizeY': 8},  # Donnees generales
    'a1b2c3d4-d600-4000-a000-000000000101': {'col': 4,  'row': 12, 'sizeX': 3, 'sizeY': 8},  # PAC HP1
    'a1b2c3d4-d600-4000-a000-000000000102': {'col': 7,  'row': 12, 'sizeX': 3, 'sizeY': 8},  # PAC HP2
    'a1b2c3d4-d600-4000-a000-000000000103': {'col': 10, 'row': 12, 'sizeX': 3, 'sizeY': 8},  # PAC HP3
    'a1b2c3d4-d600-4000-a000-000000000104': {'col': 13, 'row': 12, 'sizeX': 3, 'sizeY': 8},  # PAC HP4
    'a1b2c3d4-d600-4000-a000-000000000202': {'col': 16, 'row': 12, 'sizeX': 4, 'sizeY': 8},  # Chauffage
    'a1b2c3d4-d600-4000-a000-000000000201': {'col': 20, 'row': 12, 'sizeX': 4, 'sizeY': 8},  # ECS
}

PAC_HP_WIDGETS = {
    'a1b2c3d4-d600-4000-a000-000000000101': 1,
    'a1b2c3d4-d600-4000-a000-000000000102': 2,
    'a1b2c3d4-d600-4000-a000-000000000103': 3,
    'a1b2c3d4-d600-4000-a000-000000000104': 4,
}


def hide_absent_snippet(hp_idx):
    return f'''
// {HIDE_MARKER} : hide widget if HP{hp_idx} is not present (comm != true)
if (data && data[0] && data[0].HP{hp_idx}_comm !== true && data[0].HP{hp_idx}_comm !== 'true') {{
    return '<div class="pac-absent-host" style="display:none"></div>';
}}
'''


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
    backup_path = f'scripts/tb/dashboard/backup/mes-installations.reorg.{ts}.json'
    with open(backup_path, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup_path}')

    print('\n=== Step 2a: Apply layout updates ===')
    widgets = dash['configuration']['widgets']
    lyt = dash['configuration']['states']['default']['layouts']['main']['widgets']
    for wid, new_lyt in LAYOUT_UPDATES.items():
        if wid not in lyt:
            print(f'  SKIP {wid} (not in default state)')
            continue
        old = dict(lyt[wid])
        lyt[wid].update(new_lyt)
        if wid in widgets:
            widgets[wid].update({k: new_lyt[k] for k in ('col', 'row', 'sizeX', 'sizeY')})
        title = widgets.get(wid, {}).get('config', {}).get('title', '?')
        print(f'  [{title:25s}]  {old.get("col"):>2},{old.get("row"):>3}  {old.get("sizeX")}x{old.get("sizeY"):<3}  ->  {new_lyt["col"]:>2},{new_lyt["row"]:>3}  {new_lyt["sizeX"]}x{new_lyt["sizeY"]}')

    print('\n=== Step 2b: Inject hide-absent snippets ===')
    for wid, hp_idx in PAC_HP_WIDGETS.items():
        w = widgets.get(wid)
        if not w:
            continue
        title = w['config'].get('title', '?')
        md = w['config']['settings'].get('markdownTextFunction', '')
        if HIDE_MARKER in md:
            print(f'  [{title:25s}]  ALREADY present (idempotent)')
            continue
        snippet = hide_absent_snippet(hp_idx)
        shim_marker = '__PACV2_SHIM__'
        if shim_marker not in md:
            print(f'  SKIP {title} : no pac_v2 shim found')
            continue
        shim_pos = md.find(shim_marker)
        iife_end = md.find('})();', shim_pos)
        if iife_end < 0:
            print(f'  SKIP {title} : could not locate IIFE end')
            continue
        insert_at = iife_end + len('})();')
        md_new = md[:insert_at] + '\n' + snippet + md[insert_at:]
        w['config']['settings']['markdownTextFunction'] = md_new
        print(f'  [{title:25s}]  injected hide-absent for hp={hp_idx}')

    print('\n=== Step 3: POST ===')
    if args.dry_run:
        preview = f'scripts/tb/dashboard/backup/mes-installations.reorg.preview.{ts}.json'
        with open(preview, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'DRY-RUN. Preview: {preview}')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

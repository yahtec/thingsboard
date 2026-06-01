#!/usr/bin/env python3
"""
Phase 3.3 propre : replace markdown_card widget instances on "Mes Installations"
with refactored TDUO widgets, AND resize the dashboard layout to fit the new
landscape widget dimensions.

Cf. spec docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md
    Section 7.3.

Usage:
  replace-widgets.py --pwd <password> [--dry-run]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

DASHBOARD_ID  = '0964da30-3e56-11f1-bbfe-e1395562cba0'
ENTITY_ALIAS  = '79b58a10-d4bf-f798-68ca-0476518eb725'  # 'Chaufferie selectionnee'
BASE_URL      = 'https://thingsboard.tsmart.fr'

# Per-widget replacement plan.
# Each entry includes : the widget instance ID, source state, new fqn,
# descriptor type, optional hpIndex/mode/navigateTo settings, AND the NEW
# layout position (state, col, row, sizeX, sizeY).
REPLACEMENTS = [
    # ----- State 'default' --------------------------------------------------
    # Hub Info : bannière full-width (24x3) au-dessus des PAC tiles
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000001', 'state': 'default',
     'title': 'Données générales', 'fqn': 'tenant.tduo.hub_info',
     'desc_type': 'latest', 'settings': {'mode': 'hero'},
     'layout': {'col': 0, 'row': 7, 'sizeX': 24, 'sizeY': 3}},
    # 4 PAC Synoptic landscape : 2 par ligne (12x6 each)
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000101', 'state': 'default',
     'title': 'PAC HP1', 'fqn': 'tenant.tduo.pac_synoptic',
     'desc_type': 'latest', 'settings': {'hpIndex': 1, 'navigateTo': 'donnees_HP1'},
     'layout': {'col': 0,  'row': 10, 'sizeX': 12, 'sizeY': 6}},
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000102', 'state': 'default',
     'title': 'PAC HP2', 'fqn': 'tenant.tduo.pac_synoptic',
     'desc_type': 'latest', 'settings': {'hpIndex': 2, 'navigateTo': 'donnees_HP1'},
     'layout': {'col': 12, 'row': 10, 'sizeX': 12, 'sizeY': 6}},
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000103', 'state': 'default',
     'title': 'PAC HP3', 'fqn': 'tenant.tduo.pac_synoptic',
     'desc_type': 'latest', 'settings': {'hpIndex': 3, 'navigateTo': 'donnees_HP1'},
     'layout': {'col': 0,  'row': 16, 'sizeX': 12, 'sizeY': 6}},
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000104', 'state': 'default',
     'title': 'PAC HP4', 'fqn': 'tenant.tduo.pac_synoptic',
     'desc_type': 'latest', 'settings': {'hpIndex': 4, 'navigateTo': 'donnees_HP1'},
     'layout': {'col': 12, 'row': 16, 'sizeX': 12, 'sizeY': 6}},
    # ECS + Chauffage cote a cote (12x4 each) en bas
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000201', 'state': 'default',
     'title': 'ECS', 'fqn': 'tenant.tduo.dhw_card',
     'desc_type': 'latest', 'settings': {},
     'layout': {'col': 0,  'row': 22, 'sizeX': 12, 'sizeY': 4}},
    {'wid': 'a1b2c3d4-d600-4000-a000-000000000202', 'state': 'default',
     'title': 'Chauffage', 'fqn': 'tenant.tduo.heating_loop_card',
     'desc_type': 'latest', 'settings': {},
     'layout': {'col': 12, 'row': 22, 'sizeX': 12, 'sizeY': 4}},
    # ----- State 'donnees_HP1' ----------------------------------------------
    # PAC Synoptic plein écran (sous Topbar + Action button + HTML Card)
    {'wid': '49e69aac-15bc-32c4-c32d-c474cfeffa82', 'state': 'donnees_HP1',
     'title': 'PAC Info', 'fqn': 'tenant.tduo.pac_synoptic',
     'desc_type': 'latest', 'settings': {'hpIndex': 1},
     'layout': {'col': 0, 'row': 1, 'sizeX': 24, 'sizeY': 6}},
    # Boiler Synoptic plein
    {'wid': 'a1b2c3d4-0002-4000-a000-000000000002', 'state': 'donnees_HP1',
     'title': 'Chaudière Info', 'fqn': 'tenant.tduo.boiler_synoptic',
     'desc_type': 'latest', 'settings': {'hpIndex': 1},
     'layout': {'col': 0, 'row': 7, 'sizeX': 24, 'sizeY': 5}},
]

# Layout adjustments for OTHER widgets (untouched widgets) to fit around
# the new landscape grid. Keyed by widget id ; only the layout dict is changed.
LAYOUT_ADJUST = {
    'donnees_HP1': {
        # Decaler Timeline + PAC Chart + Chaudiere Chart + Usage Pie sous le Boiler Synoptic
        # Topbar reste row 0 (24x1), Action button row 1 (3x1), HTML Card row 1 col 3 (1x1)
        # PAC Synoptic row 1..6, Boiler Synoptic row 7..11, Timeline row 12.5...
        'a1b2c3d4-0400-4000-a000-000000000001': {'col': 0, 'row': 12.5, 'sizeX': 24, 'sizeY': 1.5},  # Timeline
        'a1b2c3d4-0001-4000-a000-000000000001': {'col': 0, 'row': 14,   'sizeX': 24, 'sizeY': 8},    # PAC Chart
        'a1b2c3d4-0003-4000-a000-000000000003': {'col': 0, 'row': 22,   'sizeX': 24, 'sizeY': 8},    # Chaudiere Chart
        'a1b2c3d4-9997-4000-a000-000000000097': {'col': 0, 'row': 30,   'sizeX': 24, 'sizeY': 8},    # Usage Pie
    }
}


def http_get(path, token):
    req = urllib.request.Request(f'{BASE_URL}{path}', headers={'X-Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def http_post(path, body_obj, token, timeout=300):
    body = json.dumps(body_obj, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE_URL}{path}',
        data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {token}'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
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


def fetch_widget_type_ids(token):
    fqn_to_id = {}
    page = 0
    while True:
        resp = http_get(f'/api/widgetTypes?pageSize=200&page={page}&textSearch=', token)
        for w in resp.get('data', []):
            fqn_to_id[w['fqn']] = w['id']['id']
        if not resp.get('hasNext'):
            break
        page += 1
    return fqn_to_id


def build_widget_config(title, settings):
    return {
        'title': title,
        'showTitle': False,
        'backgroundColor': 'transparent',
        'color': '#F5F5F7',
        'padding': '0',
        'settings': dict(settings),
        'datasources': [{
            'type': 'entity',
            'dataKeys': [{'name': 'pac_v2', 'type': 'timeseries', 'label': 'pac_v2',
                          'color': '#1976d2', 'settings': {}}],
            'entityAliasId': ENTITY_ALIAS,
        }],
        'configMode': 'basic',
        'actions': {},
        'dropShadow': False,
        'enableFullscreen': False,
        'widgetStyle': {},
        'titleStyle': {'fontSize': '14px', 'fontWeight': '600', 'color': '#F5F5F7'},
        'useDashboardTimewindow': True,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    print('=== Step 1: Login + widget types ===')
    token = login(args.user, args.pwd)
    fqn_to_id = fetch_widget_type_ids(token)
    def lookup(fqn):
        for c in (fqn, fqn.replace('tenant.', '', 1)):
            if c in fqn_to_id:
                return fqn_to_id[c]
        sys.exit(f'Widget type {fqn} not found')
    fqn_resolved = {}
    for fqn in {r['fqn'] for r in REPLACEMENTS}:
        fqn_resolved[fqn] = lookup(fqn)
        print(f'  {fqn} -> {fqn_resolved[fqn]}')

    print('\n=== Step 2: Fetch dashboard ===')
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Title: {dash["title"]}  version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup_path = f'scripts/tb/dashboard/backup/mes-installations.python.{ts}.json'
    with open(backup_path, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup_path}')

    print('\n=== Step 3: Patch widget definitions + layout ===')
    widgets = dash['configuration']['widgets']
    states = dash['configuration']['states']
    for r in REPLACEMENTS:
        wid = r['wid']
        if wid not in widgets:
            print(f'  SKIP {wid} (widget def not found)')
            continue
        w = widgets[wid]
        # Update widget definition
        w['type'] = r['desc_type']
        w['typeFullFqn'] = r['fqn']
        w['typeId'] = {'entityType': 'WIDGET_TYPE', 'id': fqn_resolved[r['fqn']]}
        w['config'] = build_widget_config(r['title'], r['settings'])
        for legacy in ('bundleAlias', 'typeAlias'):
            if legacy in w:
                w[legacy] = ''
        # Update layout
        lyt = states[r['state']]['layouts']['main']['widgets']
        if wid in lyt:
            lyt[wid].update(r['layout'])
        print(f"  {wid} [{r['state']}/{r['title']}] -> {r['fqn']} layout={r['layout']}")

    # Apply other layout adjustments
    for state, adjustments in LAYOUT_ADJUST.items():
        lyt = states[state]['layouts']['main']['widgets']
        for wid, new_lyt in adjustments.items():
            if wid in lyt:
                lyt[wid].update(new_lyt)
                print(f"  ADJUST {wid} [{state}] layout={new_lyt}")

    print('\n=== Step 4: POST ===')
    if args.dry_run:
        preview = f'scripts/tb/dashboard/backup/mes-installations.python.preview.{ts}.json'
        with open(preview, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'DRY-RUN. Preview: {preview}')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')
    print(f'\n=== DONE ===')
    print(f'Rollback: restore-config.py {backup_path} {DASHBOARD_ID} {BASE_URL} <user> <pwd>')


if __name__ == '__main__':
    main()

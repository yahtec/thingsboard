#!/usr/bin/env python3
"""
Restaure l'architecture du dashboard unite_backup sur 'Mes Installations' :
- UN seul widget Markdown qui rend DG + PAC1..nHp + ECS/Chauffage (conditionnels)
  via JS interne (boucle for + if sur type) -- collapse natif des PAC absentes
- Retire PAC HP1..4, ECS, Chauffage du layout default (widgets defs restent)
- Layout : Topbar, Navbar, Photo, Map en haut ; big widget plein ecran row 8
- gridSettings : retire minColumns, mobileAutoFillHeight=false
- Applique le shim pac_v2 (data wired sur pac_v2, pas les flat keys)

Idempotent via marker.

Usage:
  restore-unite-architecture.py --pwd <pwd> [--dry-run]
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID         = '0964da30-3e56-11f1-bbfe-e1395562cba0'
UNITE_BACKUP_ID      = '98a2bf81-33cc-41f9-9a5a-75f11869ce3d'
BASE_URL             = 'https://thingsboard.tsmart.fr'
DG_WIDGET_ID         = 'a1b2c3d4-d600-4000-a000-000000000001'  # layout key
ENTITY_ALIAS         = '79b58a10-d4bf-f798-68ca-0476518eb725'
MARKER               = '__UNITE_ARCH_RESTORED__'
SHIM_MARKER          = '__PACV2_SHIM__'

# Widgets a retirer du layout default (mais on garde leurs defs au cas ou)
WIDGETS_TO_UNLINK = [
    'a1b2c3d4-d600-4000-a000-000000000101',  # PAC HP1
    'a1b2c3d4-d600-4000-a000-000000000102',  # PAC HP2
    'a1b2c3d4-d600-4000-a000-000000000103',  # PAC HP3
    'a1b2c3d4-d600-4000-a000-000000000104',  # PAC HP4
    'a1b2c3d4-d600-4000-a000-000000000201',  # ECS
    'a1b2c3d4-d600-4000-a000-000000000202',  # Chauffage
]

# pac_v2 shim (depuis rewire-markdown-pac-v2.py)
SHIM_CODE = '''// __PACV2_SHIM__ : remap pac_v2 nested -> flat dict
var PACV2_FLATTEN = function(p) {
    var out = {};
    if (!p || typeof p !== 'object') return out;
    for (var __k in p) {
        var __v = p[__k];
        if (__v === null || __v === undefined) continue;
        if (typeof __v !== 'object') out[__k] = __v;
    }
    if (Array.isArray(p.HPs)) {
        for (var __i = 0; __i < p.HPs.length; __i++) {
            var __hp = p.HPs[__i] || {}, __pfx = 'HP' + (__i + 1);
            if (__hp.HP)     for (var __k2 in __hp.HP)     out[__pfx + '_' + __k2] = __hp.HP[__k2];
            if (__hp.invert) for (var __k2 in __hp.invert) out[__pfx + '_invert_' + __k2] = __hp.invert[__k2];
            if (__hp.boil)   for (var __k2 in __hp.boil)   out[__pfx + '_boil_' + __k2] = __hp.boil[__k2];
            if (__hp.pump)   for (var __k2 in __hp.pump)   out[__pfx + '_pump_' + __k2] = __hp.pump[__k2];
            ['comm', 'relStm', 'relEsp', 'relScr'].forEach(function(__k3) {
                if (__hp[__k3] !== undefined) out[__pfx + '_' + __k3] = __hp[__k3];
            });
        }
    }
    if (p.dhw) {
        for (var __k in p.dhw) {
            var __v = p.dhw[__k];
            if (__v === null || __v === undefined) continue;
            var __m = __k.match(/^pump([1-4])$/);
            if (__m && typeof __v === 'object') {
                for (var __k2 in __v) out['dhw_pump' + __m[1] + '_' + __k2] = __v[__k2];
            } else if (typeof __v !== 'object') {
                out['dhw_' + __k] = __v;
            }
        }
    }
    if (p.heat) {
        for (var __k in p.heat) {
            var __v = p.heat[__k];
            if (__v === null || __v === undefined) continue;
            if (__k === 'calo' && typeof __v === 'object') {
                for (var __k2 in __v) out['heat_calo_' + __k2] = __v[__k2];
            } else if (typeof __v !== 'object') {
                out['heat_' + __k] = __v;
            }
        }
    }
    if (p.caloM) {
        for (var __k in p.caloM) {
            var __v = p.caloM[__k];
            if (__v !== null && __v !== undefined && typeof __v !== 'object') out['caloM_' + __k] = __v;
        }
    }
    ['pump1M', 'pump2M'].forEach(function(__name) {
        if (p[__name]) {
            for (var __k in p[__name]) {
                var __v = p[__name][__k];
                if (__v !== null && __v !== undefined && typeof __v !== 'object') out[__name + '_' + __k] = __v;
            }
        }
    });
    return out;
};
(function() {
    var __ds = (data && data[0]) || null;
    if (!__ds) return;
    var __pv = __ds.pac_v2;
    if (typeof __pv === 'string') { try { __pv = JSON.parse(__pv); } catch(_) { __pv = null; } }
    if (__pv) {
        // Preserve les meta originaux (entityName, entityLabel, etc.)
        var __out = PACV2_FLATTEN(__pv);
        for (var __k in __ds) {
            if (__k !== 'pac_v2' && !(__k in __out)) __out[__k] = __ds[__k];
        }
        data = [__out];
    }
})();

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
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    token = login(args.user, args.pwd)

    print('=== Step 1: Fetch source unite_backup + target dashboard ===')
    src = http_get(f'/api/dashboard/{UNITE_BACKUP_ID}', token)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Source unite_backup version: {src["version"]}')
    print(f'Target dashboard version: {dash["version"]}')

    # Find the big widget in unite_backup (system.cards.markdown_card with sizeX>=24, sizeY>=5)
    src_ws = src['configuration']['widgets']
    src_lyt = src['configuration']['states']['default']['layouts']['main']['widgets']
    big_src_wid = None
    big_src_lyt = None
    for wid, pos in src_lyt.items():
        if pos.get('sizeX', 0) >= 24 and pos.get('sizeY', 0) >= 5:
            w = src_ws.get(wid, {})
            if w.get('typeFullFqn') == 'system.cards.markdown_card':
                big_src_wid = wid
                big_src_lyt = pos
                break
    if not big_src_wid:
        sys.exit('Big widget not found in unite_backup')
    big_src = src_ws[big_src_wid]
    print(f'Source big widget : {big_src_wid}  size {big_src_lyt["sizeX"]}x{big_src_lyt["sizeY"]} row {big_src_lyt["row"]}')

    # Backup target
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.unite-arch.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup}')

    print('\n=== Step 2: Patch DG widget with unite_backup content ===')
    dg = dash['configuration']['widgets'][DG_WIDGET_ID]
    if MARKER in dg['config']['settings'].get('markdownTextFunction', ''):
        print('  DG already patched (idempotent)')
    else:
        # Replace markdownTextFunction + markdownCss with the unite_backup versions
        src_md = big_src['config']['settings']['markdownTextFunction']
        src_css = big_src['config']['settings']['markdownCss']

        # Prepend shim + marker to markdownTextFunction
        # Marker comment for idempotence detection
        new_md = f'// {MARKER}\n' + SHIM_CODE + src_md

        dg['config']['settings']['markdownTextFunction'] = new_md
        dg['config']['settings']['markdownCss'] = src_css
        dg['config']['settings']['useMarkdownTextFunction'] = True

        # Reduce datasources to single pac_v2 key
        dg['config']['datasources'] = [{
            'type': 'entity',
            'name': '',
            'dataKeys': [{
                'name': 'pac_v2',
                'type': 'timeseries',
                'label': 'pac_v2',
                'color': '#1976d2',
                'settings': {}
            }],
            'entityAliasId': ENTITY_ALIAS,
        }]
        print('  DG widget patched : unite_backup content + pac_v2 shim')

    print('\n=== Step 3: Update DG layout (full-width, row 8) ===')
    def_lyt = dash['configuration']['states']['default']['layouts']['main']['widgets']
    # Place DG big widget as in unite_backup : col 0, row 8, 24x7, mobileHeight 17
    dg_layout = {
        'col': 0, 'row': 8, 'sizeX': 24, 'sizeY': 7,
        'mobileOrder': big_src_lyt.get('mobileOrder', 4),
        'mobileHeight': 17,
    }
    if DG_WIDGET_ID in def_lyt:
        def_lyt[DG_WIDGET_ID].update(dg_layout)
        if DG_WIDGET_ID in dash['configuration']['widgets']:
            dash['configuration']['widgets'][DG_WIDGET_ID].update({
                'col': 0, 'row': 8, 'sizeX': 24, 'sizeY': 7,
            })
    print(f'  DG layout : col 0, row 8, 24x7, mobileHeight 17')

    print('\n=== Step 4: Unlink PAC HP1..4, ECS, Chauffage from default layout ===')
    for wid in WIDGETS_TO_UNLINK:
        if wid in def_lyt:
            del def_lyt[wid]
            print(f'  Removed {wid} from default state layout')

    print('\n=== Step 5: Fix gridSettings ===')
    grid = dash['configuration']['states']['default']['layouts']['main'].get('gridSettings', {})
    if 'minColumns' in grid:
        del grid['minColumns']
        print('  Removed minColumns')
    if grid.get('mobileAutoFillHeight') is True:
        grid['mobileAutoFillHeight'] = False
        print('  mobileAutoFillHeight True -> False')
    if grid.get('autoFillHeight') is True:
        grid['autoFillHeight'] = False
        print('  autoFillHeight True -> False')
    dash['configuration']['states']['default']['layouts']['main']['gridSettings'] = grid

    # Also reset Photo + Map from unite_backup sizes : Photo 8x6, Map 16x6 row 2
    print('\n=== Step 6: Restore photo + map layout (from unite_backup) ===')
    PHOTO_ID = 'be5e1a3a-74e5-7f97-d422-4030e48fcf95'
    MAP_ID   = '1a5b4c03-ba38-ad06-5f7a-b82453a7807d'
    NAV_ID   = 'a1b2c3d4-0100-4000-a000-000000000010'
    # Place Photo + Map at row 2 like unite_backup (Topbar/Navbar at row 0-1)
    # Note : 'Mes Installations' has Navbar (not Topbar) row 0 sizeY 2.
    if PHOTO_ID in def_lyt:
        def_lyt[PHOTO_ID].update({'col': 0, 'row': 2, 'sizeX': 8, 'sizeY': 6, 'mobileOrder': 2, 'mobileHeight': 5})
        dash['configuration']['widgets'][PHOTO_ID].update({'col': 0, 'row': 2, 'sizeX': 8, 'sizeY': 6})
        print('  Photo : col 0, row 2, 8x6, mobileHeight 5')
    if MAP_ID in def_lyt:
        def_lyt[MAP_ID].update({'col': 8, 'row': 2, 'sizeX': 16, 'sizeY': 6, 'mobileOrder': 3, 'mobileHeight': 7})
        dash['configuration']['widgets'][MAP_ID].update({'col': 8, 'row': 2, 'sizeX': 16, 'sizeY': 6})
        print('  Map   : col 8, row 2, 16x6, mobileHeight 7')

    print('\n=== Step 7: POST ===')
    if args.dry_run:
        preview = f'scripts/tb/dashboard/backup/mes-installations.unite-arch.preview.{ts}.json'
        with open(preview, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'DRY-RUN. Preview: {preview}')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

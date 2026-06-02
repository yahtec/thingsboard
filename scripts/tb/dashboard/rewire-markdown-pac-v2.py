#!/usr/bin/env python3
"""
Re-cable les markdown_cards du dashboard pour qu'ils lisent pac_v2 json_v
plutot que les 30+ flat keys. Le DESIGN (HTML/CSS/template JS) reste intact.

Mecanisme :
  - Datasource reduit a 1 cle : pac_v2 (timeseries)
  - Au debut de markdownTextFunction, on injecte :
      var PACV2_FLATTEN = function(p) {...}  // remap pac_v2 -> flat dict
      var __rawDs = data[0] || {};
      var __pv = __rawDs.pac_v2;
      if (typeof __pv === 'string') { try { __pv = JSON.parse(__pv); } catch(_) { __pv = null; } }
      data = __pv ? [PACV2_FLATTEN(__pv)] : data;
  - Le `var e = data[0] || {}` reste apres -> recoit l'objet plat.
  - Le reste du template (e.HP1_status, e.tExt, e.dhw_tTank, etc.) inchange.

Idempotent : detecte la presence du marqueur __PACV2_SHIM__ et skip.

Usage:
  rewire-markdown-pac-v2.py --pwd <pwd> [--dry-run] [--only <widget_id>]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
ENTITY_ALIAS = '79b58a10-d4bf-f798-68ca-0476518eb725'
BASE_URL     = 'https://thingsboard.tsmart.fr'
SHIM_MARKER  = '__PACV2_SHIM__'

# Widgets cibles : markdown_cards de type 'latest' qui lisent des flat keys.
# On laisse les chart markdown_cards (PAC Chart, Chaudiere Chart) hors scope --
# elles utilisent des timeseries qui demandent un parser JSON par echantillon.
TARGETS = [
    # default state
    'a1b2c3d4-d600-4000-a000-000000000001',  # Donnees generales
    'a1b2c3d4-d600-4000-a000-000000000101',  # PAC HP1
    'a1b2c3d4-d600-4000-a000-000000000102',  # PAC HP2
    'a1b2c3d4-d600-4000-a000-000000000103',  # PAC HP3
    'a1b2c3d4-d600-4000-a000-000000000104',  # PAC HP4
    'a1b2c3d4-d600-4000-a000-000000000201',  # ECS
    'a1b2c3d4-d600-4000-a000-000000000202',  # Chauffage
    # donnees_HP1 state -- type=timeseries mais display latest
    '49e69aac-15bc-32c4-c32d-c474cfeffa82',  # PAC Info
    'a1b2c3d4-0002-4000-a000-000000000002',  # Chaudiere Info
]

# Shim code injecte au debut de markdownTextFunction. Reproduit le mapping
# inverse du dispatcher (forward : nested -> flat).
SHIM_CODE = '''// __PACV2_SHIM__ : remap pac_v2 nested -> flat dict (compat ancien template)
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
    if (__pv) { data = [PACV2_FLATTEN(__pv)]; }
})();

'''


def http_get(path, token):
    req = urllib.request.Request(f'{BASE_URL}{path}', headers={'X-Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def http_post(path, body_obj, token):
    body = json.dumps(body_obj, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE_URL}{path}',
        data=body,
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


def rewire_widget(w):
    """Mutate `w` in place. Return (changed: bool, info: str)."""
    cfg = w['config']
    md = cfg.get('settings', {}).get('markdownTextFunction', '')
    if not md:
        return False, 'no markdownTextFunction'
    if SHIM_MARKER in md:
        return False, 'shim already present (idempotent)'
    # Replace datasources : keep first datasource shape but reduce dataKeys to pac_v2 only.
    if not cfg.get('datasources'):
        return False, 'no datasources'
    ds0 = cfg['datasources'][0]
    old_count = len(ds0.get('dataKeys', []))
    ds0['dataKeys'] = [{
        'name': 'pac_v2',
        'type': 'timeseries',
        'label': 'pac_v2',
        'color': '#1976d2',
        'settings': {},
    }]
    # Keep alias if present, else set ours.
    if not ds0.get('entityAliasId') and not ds0.get('deviceAliasId'):
        ds0['entityAliasId'] = ENTITY_ALIAS
    cfg['datasources'] = [ds0]
    # Prepend shim to markdownTextFunction.
    cfg['settings']['markdownTextFunction'] = SHIM_CODE + md
    return True, f'shim prepended, dataKeys {old_count} -> 1 (pac_v2)'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--only', help='limit to single widget id')
    args = ap.parse_args()

    targets = [args.only] if args.only else TARGETS

    print('=== Step 1: Login + fetch dashboard ===')
    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Version: {dash["version"]}')

    ts = time.strftime('%Y%m%d-%H%M%S')
    backup_path = f'scripts/tb/dashboard/backup/mes-installations.rewire.{ts}.json'
    with open(backup_path, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup_path}')

    print('\n=== Step 2: Rewire markdown_cards ===')
    widgets = dash['configuration']['widgets']
    any_changed = False
    for wid in targets:
        w = widgets.get(wid)
        if not w:
            print(f'  SKIP {wid} (not in dashboard)')
            continue
        title = w['config'].get('title', '?')
        if w.get('typeFullFqn') != 'system.cards.markdown_card':
            print(f'  SKIP {wid} ({title!r}) -- not markdown_card (fqn={w.get("typeFullFqn")})')
            continue
        changed, info = rewire_widget(w)
        marker = 'OK' if changed else 'SKIP'
        print(f'  [{marker}] {wid} {title!r:35s} -- {info}')
        any_changed = any_changed or changed

    if not any_changed:
        print('\nNo changes -- exiting.')
        return

    print('\n=== Step 3: POST ===')
    if args.dry_run:
        preview = f'scripts/tb/dashboard/backup/mes-installations.rewire.preview.{ts}.json'
        with open(preview, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'DRY-RUN. Preview: {preview}')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Re-cable les chart widgets (PAC Chart, Chaudiere Chart) sur pac_v2.

Les charts fetch via /api/plugins/telemetry/DEVICE/.../timeseries?keys=HP1_tCond,...
Probleme : ces flat keys ne sont plus ecrites depuis le 29 mai (rule chain v2
ne flattenne plus le payload nested). Les charts montrent des series vides.

Shim approach :
1. Prepend la fn PACV2_FLATTEN (meme que markdown shim)
2. Find/replace : keys = SERIES.map(...).join(',')  ->  keys = 'pac_v2'
3. Find/replace : la callback `.then(function(d) { seriesData = d; ...`
   On insere AVANT `seriesData = d;` un bloc qui reconstitue d depuis pac_v2 :
     for each point pv in d.pac_v2 : flatten(JSON.parse(pv.value)) -> ajouter
     les valeurs aux series attendues.

Idempotent via marker __PACV2_CHART_SHIM__.

Usage:
  rewire-charts-pac-v2.py --pwd <pwd> [--dry-run]
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
MARKER       = '__PACV2_CHART_SHIM__'

CHART_WIDGETS = {
    'a1b2c3d4-0001-4000-a000-000000000001': 'PAC Chart',
    'a1b2c3d4-0003-4000-a000-000000000003': 'Chaudiere Chart',
}

# Shim a prepend dans markdownTextFunction
SHIM_HEADER = f'''// {MARKER}
function PACV2_FLATTEN(p) {{
    var out = {{}};
    if (!p || typeof p !== 'object') return out;
    for (var __k in p) {{
        var __v = p[__k];
        if (__v === null || __v === undefined) continue;
        if (typeof __v !== 'object') out[__k] = __v;
    }}
    if (Array.isArray(p.HPs)) {{
        for (var __i = 0; __i < p.HPs.length; __i++) {{
            var __hp = p.HPs[__i] || {{}}, __pfx = 'HP' + (__i + 1);
            if (__hp.HP)     for (var __k2 in __hp.HP)     out[__pfx + '_' + __k2] = __hp.HP[__k2];
            if (__hp.invert) for (var __k2 in __hp.invert) out[__pfx + '_invert_' + __k2] = __hp.invert[__k2];
            if (__hp.boil)   for (var __k2 in __hp.boil)   out[__pfx + '_boil_' + __k2] = __hp.boil[__k2];
            if (__hp.pump)   for (var __k2 in __hp.pump)   out[__pfx + '_pump_' + __k2] = __hp.pump[__k2];
            ['comm', 'relStm', 'relEsp', 'relScr'].forEach(function(__k3) {{
                if (__hp[__k3] !== undefined) out[__pfx + '_' + __k3] = __hp[__k3];
            }});
        }}
    }}
    if (p.dhw) for (var __k in p.dhw) {{
        var __v = p.dhw[__k];
        if (__v === null || __v === undefined) continue;
        var __m = __k.match(/^pump([1-4])$/);
        if (__m && typeof __v === 'object') {{
            for (var __k2 in __v) out['dhw_pump' + __m[1] + '_' + __k2] = __v[__k2];
        }} else if (typeof __v !== 'object') {{
            out['dhw_' + __k] = __v;
        }}
    }}
    if (p.heat) for (var __k in p.heat) {{
        var __v = p.heat[__k];
        if (__v === null || __v === undefined) continue;
        if (__k === 'calo' && typeof __v === 'object') {{
            for (var __k2 in __v) out['heat_calo_' + __k2] = __v[__k2];
        }} else if (typeof __v !== 'object') {{
            out['heat_' + __k] = __v;
        }}
    }}
    if (p.caloM) for (var __k in p.caloM) {{
        var __v = p.caloM[__k];
        if (__v !== null && __v !== undefined && typeof __v !== 'object') out['caloM_' + __k] = __v;
    }}
    ['pump1M', 'pump2M'].forEach(function(__name) {{
        if (p[__name]) for (var __k in p[__name]) {{
            var __v = p[__name][__k];
            if (__v !== null && __v !== undefined && typeof __v !== 'object') out[__name + '_' + __k] = __v;
        }}
    }});
    return out;
}}

// __PACV2_CHART_TRANSFORM__ : transforme un response {{pac_v2: [...]}} en
// {{HP1_tCond: [...], HP1_tEvap: [...], ...}} attendu par le code chart.
function PACV2_TO_SERIES(d, expectedKeys) {{
    var pacPoints = d.pac_v2 || [];
    var newSeries = {{}};
    expectedKeys.forEach(function(k) {{ newSeries[k] = []; }});
    pacPoints.forEach(function(p) {{
        var ts = parseInt(p.ts, 10);
        var raw = p.value;
        try {{
            var pv = (typeof raw === 'string') ? JSON.parse(raw) : raw;
            var flat = PACV2_FLATTEN(pv);
            expectedKeys.forEach(function(k) {{
                var v = flat[k];
                if (v !== null && v !== undefined) {{
                    newSeries[k].push({{ ts: ts, value: v }});
                }}
            }});
        }} catch (e) {{}}
    }});
    return newSeries;
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


def patch_chart_md(md):
    """Returns (new_md, info_str). Idempotent."""
    if MARKER in md:
        return md, 'already patched'
    # Step 1: prepend shim header
    new_md = SHIM_HEADER + md

    # Step 2: replace keys=SERIES.map line
    old_keys = "var keys = SERIES.map(function(s) { return s.key; }).join(',');"
    new_keys = ("var __expectedKeys = SERIES.map(function(s) { return s.key; });\n"
                "        var keys = 'pac_v2';  // __PACV2_CHART_SHIM__")
    if old_keys not in new_md:
        return md, 'PATCH FAIL: keys SERIES.map pattern not found'
    new_md = new_md.replace(old_keys, new_keys)

    # Step 3: insert transform before `seriesData = d;`
    old_assign = 'seriesData = d;'
    new_assign = ('d = PACV2_TO_SERIES(d, __expectedKeys);  // __PACV2_CHART_SHIM__\n'
                  '                seriesData = d;')
    if old_assign not in new_md:
        return md, 'PATCH FAIL: seriesData = d not found'
    new_md = new_md.replace(old_assign, new_assign, 1)
    return new_md, 'patched OK'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.charts.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup}')

    widgets = dash['configuration']['widgets']
    for wid, name in CHART_WIDGETS.items():
        if wid not in widgets:
            print(f'  SKIP {name} (not found)')
            continue
        w = widgets[wid]
        md = w['config']['settings'].get('markdownTextFunction', '')
        new_md, info = patch_chart_md(md)
        if new_md != md:
            w['config']['settings']['markdownTextFunction'] = new_md
        print(f'  [{name}] {info}  ({len(md)} -> {len(new_md)} chars)')

    if args.dry_run:
        preview = f'scripts/tb/dashboard/backup/mes-installations.charts.preview.{ts}.json'
        with open(preview, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'DRY-RUN. Preview: {preview}')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

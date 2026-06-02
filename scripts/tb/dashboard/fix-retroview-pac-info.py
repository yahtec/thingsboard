#!/usr/bin/env python3
"""
Patche le widget PAC Info pour respecter le mode retroview :
- Si sessionStorage.tduo.retroview.endTs est defini, fetch pac_v2 a ce ts
  via XHR synchrone (deprecated mais fonctionnel)
- Sinon comportement actuel (latest live via data[0])

Idempotent via marker __PACV2_RETROVIEW_SHIM__.

Usage:
  fix-retroview-pac-info.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
# Widgets a patcher avec le retroview shim (memes shim format pac_v2)
TARGETS = [
    ('49e69aac-15bc-32c4-c32d-c474cfeffa82', 'PAC Info'),
    ('a1b2c3d4-0002-4000-a000-000000000002', 'Chaudiere Info'),
]
MARKER       = '__PACV2_RETROVIEW_SHIM__'

OLD_SHIM = '''(function() {
    var __ds = (data && data[0]) || null;
    if (!__ds) return;
    var __pv = __ds.pac_v2;
    if (typeof __pv === 'string') { try { __pv = JSON.parse(__pv); } catch(_) { __pv = null; } }
    if (__pv) { data = [PACV2_FLATTEN(__pv)]; }
})();'''

NEW_SHIM = '''(function() {
    // ''' + MARKER + ''' : respecter le mode retroview
    var __ds = (data && data[0]) || null;
    if (!__ds) return;
    var __pv = null;

    // 1. Si retroview actif : fetch sync a sessionStorage.tduo.retroview.endTs
    try {
        var __rvEndTs = sessionStorage.getItem('tduo.retroview.endTs');
        if (__rvEndTs) {
            var __ctxRef = (typeof ctx !== 'undefined' && ctx) ? ctx
                          : (typeof self !== 'undefined' && self.ctx ? self.ctx : null);
            var __ds0 = (__ctxRef && __ctxRef.datasources && __ctxRef.datasources[0]) || null;
            var __devId = __ds0 && (__ds0.entityId || (__ds0.entity && __ds0.entity.id && __ds0.entity.id.id));
            if (__devId) {
                var __end = parseInt(__rvEndTs, 10);
                var __url = '/api/plugins/telemetry/DEVICE/' + __devId +
                            '/values/timeseries?keys=pac_v2&startTs=0&endTs=' + __end +
                            '&limit=1&orderBy=DESC&agg=NONE';
                var __token = localStorage.getItem('jwt_token');
                var __xhr = new XMLHttpRequest();
                __xhr.open('GET', __url, false);
                if (__token) __xhr.setRequestHeader('X-Authorization', 'Bearer ' + __token);
                try {
                    __xhr.send();
                    if (__xhr.status === 200) {
                        var __resp = JSON.parse(__xhr.responseText);
                        if (__resp.pac_v2 && __resp.pac_v2.length) {
                            var __raw = __resp.pac_v2[0].value;
                            __pv = (typeof __raw === 'string') ? JSON.parse(__raw) : __raw;
                        }
                    }
                } catch (e) {}
            }
        }
    } catch (e) {}

    // 2. Fallback : data[0] live (mode normal)
    if (!__pv) {
        __pv = __ds.pac_v2;
        if (typeof __pv === 'string') { try { __pv = JSON.parse(__pv); } catch(_) { __pv = null; } }
    }

    if (__pv) { data = [PACV2_FLATTEN(__pv)]; }
})();'''


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
    backup = f'scripts/tb/dashboard/backup/mes-installations.retroviewfix.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    any_changed = False
    for wid, name in TARGETS:
        w = dash['configuration']['widgets'].get(wid)
        if not w:
            print(f'  SKIP {name} (not found)')
            continue
        md = w['config']['settings'].get('markdownTextFunction', '')
        if MARKER in md:
            print(f'  [{name}] already patched (idempotent)')
            continue
        if OLD_SHIM not in md:
            print(f'  [{name}] SKIP : OLD_SHIM pattern not found (shim format different)')
            continue
        md_new = md.replace(OLD_SHIM, NEW_SHIM, 1)
        w['config']['settings']['markdownTextFunction'] = md_new
        print(f'  [{name}] retroview shim injected ({len(md)} -> {len(md_new)} chars)')
        any_changed = True
    if not any_changed:
        print('No changes -- exiting')
        return
    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()

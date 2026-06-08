#!/usr/bin/env python3
"""
Patche les widgets "PAC Chart" et "Chaudiere Chart" du dashboard "Mes Installations"
pour afficher des bandes SVG grisees sur les periodes ou une PAC etait en defaut
de communication (clefs telemetry evt_status / evt_fault / evt_device / evt_id).

Lookback fixe : fetch sur 90 jours pour detecter les defauts initiés AVANT la
fenetre visible (cas typique d'un defaut comm qui dure plusieurs jours).

Reconstruction des intervalles : pair (evt_status=1 -> next evt_status=0) par
(device, fault_code). Un intervalle non ferme dans la fenetre = bande qui dure
jusqu'a now.

Idempotent : marker __EVT_MARKERS_PATCH__ + tag de version __EVT_INSIDE_V3__.
Les helpers sont injectes A L'INTERIEUR du setTimeout(function() {...}) du widget
pour acceder a DEVICE_ID/getToken/lastDrawnWindow via closure JS.

Usage:
  python scripts/tb/widgets/patch-pac-chart-add-evt-markers.py --pwd <pwd>
  python scripts/tb/widgets/patch-pac-chart-add-evt-markers.py --pwd <pwd> --dry-run
"""

import argparse, json, os, re, sys, time, urllib.request

BASE_URL = 'https://thingsboard.tsmart.fr'
BACKUP_DIR = os.path.join(os.path.dirname(__file__), '..', 'backup', 'widgets-tduo-v1')
MARKER = '__EVT_MARKERS_PATCH__'
V3_TAG = '__EVT_INSIDE_V3__'

TARGET_TITLES = {'PAC Chart', 'Chaudière Chart', 'Chaudiere Chart'}

# Helpers V3 - inserted INSIDE the setTimeout closure so they see
# DEVICE_ID, getToken, lastDrawnWindow via JS closure.
HELPERS_JS_V3 = r"""
    // __EVT_MARKERS_PATCH__ helpers (V3: __EVT_INSIDE_V3__) - inside setTimeout closure
    var __EVT_INTERVALS = [];
    var __EVT_LAST_FETCH = 0;
    var __EVT_LOOKBACK_DAYS = 90;
    function __EVT_FETCH() {
        if (!DEVICE_ID) return;
        if (!lastDrawnWindow) return;
        var now = Date.now();
        if (now - __EVT_LAST_FETCH < 30000) return;
        __EVT_LAST_FETCH = now;
        var endTs = now;
        var startTs = now - __EVT_LOOKBACK_DAYS * 86400000;
        var keys = 'evt_id,evt_status,evt_fault,evt_device';
        var url = '/api/plugins/telemetry/DEVICE/' + DEVICE_ID +
            '/values/timeseries?keys=' + keys +
            '&startTs=' + startTs + '&endTs=' + endTs + '&agg=NONE&limit=500&orderBy=DESC';
        fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var FAULT_CODES = {15:1,29:1,38:1,39:1,40:1,88:1};
                var PAC_DEVICES = {50:1,51:1,52:1,53:1,54:1,55:1};
                var byTs = {};
                ['evt_id','evt_status','evt_fault','evt_device'].forEach(function(k) {
                    (d[k] || []).forEach(function(dp) {
                        var ts = dp.ts;
                        if (!byTs[ts]) byTs[ts] = {ts: ts};
                        byTs[ts][k] = Number(dp.value);
                    });
                });
                var pts = Object.keys(byTs).map(function(k) { return byTs[k]; })
                    .filter(function(p) { return p.evt_status !== undefined && p.evt_fault !== undefined && p.evt_device !== undefined; })
                    .sort(function(a, b) { return a.ts - b.ts; });
                var openMap = {};
                var intervals = [];
                pts.forEach(function(p) {
                    if (!PAC_DEVICES[p.evt_device] || !FAULT_CODES[p.evt_fault]) return;
                    var realTs = p.evt_id > 0 ? p.evt_id * 1000 : p.ts;
                    var key = p.evt_device + ':' + p.evt_fault;
                    if (p.evt_status === 1) {
                        if (openMap[key] === undefined) openMap[key] = realTs;
                    } else if (p.evt_status === 0) {
                        if (openMap[key] !== undefined) {
                            intervals.push({ start: openMap[key], end: realTs });
                            delete openMap[key];
                        }
                    }
                });
                Object.keys(openMap).forEach(function(key) {
                    intervals.push({ start: openMap[key], end: Date.now() });
                });
                __EVT_INTERVALS = intervals;
                console.log('[evt-markers] reconstructed ' + intervals.length + ' interval(s) from ' + pts.length + ' point(s)');
                if (typeof drawChart === 'function') drawChart();
            })
            .catch(function(e) { console.warn('[evt-markers] fetch failed', e); });
    }
    function __EVT_RECTS(padL, padT, iw, ih, xOf, tw) {
        if (!__EVT_INTERVALS.length) return '';
        var s = '';
        __EVT_INTERVALS.forEach(function(iv) {
            var s0 = Math.max(iv.start, tw.startTs);
            var e0 = Math.min(iv.end, tw.endTs);
            if (e0 <= s0) return;
            var x0 = xOf(s0), x1 = xOf(e0);
            var bw = Math.max(1, x1 - x0);
            s += '<rect x="' + x0.toFixed(1) + '" y="' + padT + '" width="' + bw.toFixed(1) + '" height="' + ih + '" fill="#888" fill-opacity="0.18" pointer-events="none"/>';
        });
        return s;
    }
    // end __EVT_MARKERS_PATCH__"""

# Anchor for insertion : end of DEVICE_ID IIFE + blank line + Timeline comment
INSERT_ANCHOR = '    })();\n\n    // === Timeline custom'
INSERT_REPLACEMENT = '    })();\n' + HELPERS_JS_V3 + '\n\n    // === Timeline custom'

# Fresh-install anchors (for hooks)
OLD_FETCH = 'seriesData = d;'
OLD_RENDER = 'sc += \'<line x1="\'+padL+\'" y1="\'+(padT+ih)+\'" x2="\'+(padL+iw)+\'" y2="\'+(padT+ih)+\'" stroke="#bbb" stroke-width="1"/>\';'

# Regexes for stripping old V1/V2 helpers from top of file
TOP_BLOCK_RE = re.compile(
    r'^// __EVT_MARKERS_PATCH__\n.*?// end __EVT_MARKERS_PATCH__\n\n?',
    re.DOTALL
)


def http_post(p, b, t=None):
    h = {'Content-Type': 'application/json'}
    if t: h['X-Authorization'] = f'Bearer {t}'
    r = urllib.request.Request(BASE_URL + p, data=json.dumps(b).encode('utf-8'), headers=h, method='POST')
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode('utf-8'))

def http_get(p, t):
    r = urllib.request.Request(BASE_URL + p, headers={'X-Authorization': f'Bearer {t}'})
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode('utf-8'))

def login(u, p):
    return http_post('/api/auth/login', {'username': u, 'password': p})['token']


def patch_function(fn_str):
    if V3_TAG in fn_str:
        return fn_str, 'already_v3'

    # Strip old top-of-file helpers block (V1/V2) if present
    work = fn_str
    if MARKER in work:
        # Strip top-of-file helpers block
        new_work, n = TOP_BLOCK_RE.subn('', work, count=1)
        if n == 0:
            return fn_str, 'error:V1/V2 detected but TOP_BLOCK regex did not match'
        work = new_work
        # The hook lines (seriesData and rect) should still be present with their /* MARKER */ comments
        # and they will continue to work once we re-inject helpers inside the closure.
    else:
        # Fresh install: need to add the hooks too
        if OLD_FETCH not in work or OLD_RENDER not in work:
            return fn_str, 'error:fresh install anchors missing'
        new_fetch_full = OLD_FETCH + ' __EVT_FETCH(); /* ' + MARKER + ' */'
        work = work.replace(OLD_FETCH, new_fetch_full, 1)
        new_render_full = OLD_RENDER + "\n        sc += __EVT_RECTS(padL, padT, iw, ih, xOf, tw); /* " + MARKER + " */"
        work = work.replace(OLD_RENDER, new_render_full, 1)

    # Inject helpers inside the closure
    if INSERT_ANCHOR not in work:
        return fn_str, 'error:INSERT_ANCHOR not found'
    work = work.replace(INSERT_ANCHOR, INSERT_REPLACEMENT, 1)
    return work, 'patched_v3'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    ap.add_argument('--dashboard', default='Mes Installations')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime('%Y%m%d-%H%M%S')

    tok = login(args.user, args.pwd)
    res = http_get('/api/tenant/dashboards?pageSize=200&page=0', tok)
    matches = [d for d in res.get('data', []) if d['title'].lower() == args.dashboard.lower()]
    if not matches:
        sys.exit(f'No dashboard matches "{args.dashboard}".')
    dash_id = matches[0]['id']['id']
    dash = http_get(f'/api/dashboard/{dash_id}', tok)

    backup = os.path.join(BACKUP_DIR, f'Mes_Installations.before_v3.{ts}.json')
    with open(backup, 'w', encoding='utf-8') as f:
        json.dump(dash, f, ensure_ascii=False, indent=2)
    print(f'    backup: {backup}')

    widgets = dash.get('configuration', {}).get('widgets', {})
    stats = {}
    for wid, w in widgets.items():
        title = w.get('config', {}).get('title') or ''
        if title not in TARGET_TITLES:
            continue
        settings = w.get('config', {}).get('settings', {})
        fn = settings.get('markdownTextFunction') or ''
        new_fn, status = patch_function(fn)
        stats[status] = stats.get(status, 0) + 1
        print(f'    {title}: {status} ({len(fn)} -> {len(new_fn)} chars)')
        if status == 'patched_v3':
            settings['markdownTextFunction'] = new_fn

    print(f'==> Stats: {stats}')
    if 'patched_v3' not in stats:
        print('    Nothing to push.')
        return

    if args.dry_run:
        out = os.path.join(BACKUP_DIR, f'Mes_Installations.after_v3_DRY.{ts}.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(dash, f, ensure_ascii=False, indent=2)
        print(f'    [DRY] saved: {out}')
        return

    updated = http_post('/api/dashboard', dash, tok)
    print(f'    OK. New version: {updated.get("version","?")}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
State 'donnees_HP1' — eclate les courbes en timelines dediees (lisibilite).

PAC : le chart unique (10 series superposees) devient 4 charts en grille 2x2 :
  1. Pressions HP / BP            (HPn_pHi, HPn_pLo — axe 0..45 bar)
  2. Temperatures                 (HPn_tIn, HPn_tOut, tExt — axe -30..90 °C)
  3. Cycle frigorifique           (HPn_tOH, HPn_tSC, HPn_tEvap, HPn_tCond)
  4. Compresseur / Detendeur      (HPn_invert_freq, HPn_invert_pwr, HPn_dpf)

Chaudiere : le chart temperatures existant passe en demi-largeur, un 2e chart
'Bruleur / Circuit eau' est ajoute a cote :
  5. HPn_boil_rpm (0..7000 rpm), HPn_boil_qe (0..4000 L/h),
     HPn_boil_press (0..4 bar)   [cles validees sur payload prod 2026-06-11]

Le widget PAC Chart existant (a1b2c3d4-0001) est REUTILISE pour le chart
Temperatures; 4 nouveaux widgets sont crees par duplication (moteur SVG
identique, SERIES/AXIS/ids DOM/global window.* specialises par chart).

Comme les 6 charts fetchent le meme pac_v2 (~3.5 MB / 24 h), un cache de
fetch partage (window.__PACV2_FETCH, TTL 25 s, keye par url) est injecte
dans chaque chart : 1 seul fetch reseau par tick de 30 s pour la page.

Idempotent via presence du widget 0601 + marker __PAC_SPLIT_V1__.

Usage:
  split-pac-charts-4-timelines.py --pwd <pwd> [--dry-run]
  split-pac-charts-4-timelines.py --offline <backup.json>   # preview sans reseau
"""

import argparse, copy, json, os, re, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'donnees_HP1'
MARKER       = '__PAC_SPLIT_V1__'

WID_PAC_CHART  = 'a1b2c3d4-0001-4000-a000-000000000001'   # reutilise -> Temperatures
WID_BOIL_INFO  = 'a1b2c3d4-0002-4000-a000-000000000002'
WID_BOIL_CHART = 'a1b2c3d4-0003-4000-a000-000000000003'
WID_PIE        = 'a1b2c3d4-9997-4000-a000-000000000097'

WID_PRESS = 'a1b2c3d4-0601-4000-a000-000000000001'
WID_FRIG  = 'a1b2c3d4-0602-4000-a000-000000000002'
WID_COMP  = 'a1b2c3d4-0603-4000-a000-000000000003'
WID_BOIL2 = 'a1b2c3d4-0604-4000-a000-000000000004'

OLD_TITLE = 'Courbes PAC (24 heures)'

SERIES_RE = re.compile(r'var SERIES = \[[\s\S]*?\n    \];')
AXIS_RE   = re.compile(r'var AXIS = \{[\s\S]*?\};')

S_TEMP = """var SERIES = [ // __PAC_SPLIT_V1__
        { key: _prefix+'tIn',  label: 'T° entrée PAC', color: '#42a5f5', axis: 'left', unit: '°C' },
        { key: _prefix+'tOut', label: 'T° sortie PAC', color: '#ef5350', axis: 'left', unit: '°C' },
        { key: 'tExt',         label: 'T° extérieure', color: '#90a4ae', axis: 'left', unit: '°C' }
    ];"""

S_PRESS = """var SERIES = [ // __PAC_SPLIT_V1__
        { key: _prefix+'pHi', label: 'Pression HP', color: '#ef5350', axis: 'left', unit: ' bar' },
        { key: _prefix+'pLo', label: 'Pression BP', color: '#42a5f5', axis: 'left', unit: ' bar' }
    ];"""

A_PRESS = """var AXIS = {
        left: { min: 0, max: 45,    decimals: 1, side: 'left',  color: '#555', fmt: function(v){ return v.toFixed(0); } },
        freq: { min: 0, max: 120,   decimals: 0, side: 'right', color: '#66bb6a', fmt: function(v){ return v.toFixed(0); } },
        pwr:  { min: 0, max: 30000, decimals: 0, side: 'right', color: '#ab47bc', fmt: function(v){ return (v/1000).toFixed(0); } },
        dpf:  { min: 0, max: 2200,  decimals: 0, side: 'right', color: '#5c6bc0', fmt: function(v){ return v.toFixed(0); } }
    };"""

S_FRIG = """var SERIES = [ // __PAC_SPLIT_V1__
        { key: _prefix+'tOH',   label: 'Surchauffe',           color: '#fbc02d', axis: 'left', unit: '°C' },
        { key: _prefix+'tSC',   label: 'Sous-refroidissement', color: '#8d6e63', axis: 'left', unit: '°C' },
        { key: _prefix+'tEvap', label: 'T° évaporation', color: '#26c6da', axis: 'left', unit: '°C' },
        { key: _prefix+'tCond', label: 'T° condensation', color: '#ff7043', axis: 'left', unit: '°C' }
    ];"""

S_COMP = """var SERIES = [ // __PAC_SPLIT_V1__
        { key: _prefix+'invert_freq', label: 'Fréq compresseur',   color: '#66bb6a', axis: 'freq', unit: ' Hz' },
        { key: _prefix+'invert_pwr',  label: 'Puiss compresseur',  color: '#ab47bc', axis: 'pwr',  unit: ' W' },
        { key: _prefix+'dpf',         label: 'Position détendeur', color: '#5c6bc0', axis: 'dpf',  unit: ' pas' }
    ];"""

S_BOIL2 = """var SERIES = [ // __PAC_SPLIT_V1__
        { key: _prefix+'boil_qe',    label: 'Débit eau',       color: '#29b6f6', axis: 'left', unit: ' L/h' },
        { key: _prefix+'boil_rpm',   label: 'Vitesse brûleur', color: '#ff9800', axis: 'freq', unit: ' rpm' },
        { key: _prefix+'boil_press', label: 'Pression eau',    color: '#66bb6a', axis: 'dpf',  unit: ' bar' }
    ];"""

# pwr garde son slot 0..30000 : le bloc de rescale dynamique AXIS.pwr.max
# du moteur y ecrit inconditionnellement, il doit exister.
A_BOIL2 = """var AXIS = {
        left: { min: 0, max: 4000,  decimals: 0, side: 'left',  color: '#555', fmt: function(v){ return v.toFixed(0); } },
        freq: { min: 0, max: 7000,  decimals: 0, side: 'right', color: '#ff9800', fmt: function(v){ return v.toFixed(0); } },
        pwr:  { min: 0, max: 30000, decimals: 0, side: 'right', color: '#ab47bc', fmt: function(v){ return (v/1000).toFixed(0); } },
        dpf:  { min: 0, max: 4,     decimals: 1, side: 'right', color: '#66bb6a', fmt: function(v){ return v.toFixed(1); } }
    };"""

# --- cache fetch partage ---------------------------------------------------
FETCH_OLD = ("fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })\n"
             "            .then(function(r) { return r.json(); })\n"
             "            .then(function(d) {\n"
             "                d = PACV2_TO_SERIES")
FETCH_NEW = ("pacv2CachedFetch(url)\n"
             "            .then(function(d) {\n"
             "                d = PACV2_TO_SERIES")
# variante chart chaudiere : .then(function(d) { d = ... sur une seule ligne
FETCH_OLD2 = ("fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })\n"
              "            .then(function(r) { return r.json(); })\n"
              "            .then(function(d) { d = PACV2_TO_SERIES")
FETCH_NEW2 = ("pacv2CachedFetch(url)\n"
              "            .then(function(d) { d = PACV2_TO_SERIES")
HELPER_ANCHOR = '    function fetchSeries() {'
HELPER = """    // __PAC_SPLIT_V1__ : cache partage — les charts de la page fetchent le
    // meme pac_v2, on ne fait qu'un fetch reseau par fenetre de 25 s.
    function pacv2CachedFetch(url) {
        var g = window.__PACV2_FETCH = window.__PACV2_FETCH || {};
        var now = Date.now();
        if (g[url] && (now - g[url].t) < 25000) return g[url].p;
        var p = fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
            .then(function(r) { return r.json(); });
        g[url] = { t: now, p: p };
        return p;
    }
"""


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    try:
        with urllib.request.urlopen(r, timeout=60) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'GET {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def replace_series(fn, new, who):
    m = SERIES_RE.search(fn)
    if not m:
        sys.exit(f'  [{who}] bloc SERIES introuvable — moteur a change, patch a reviser')
    return fn[:m.start()] + new + fn[m.end():]


def replace_axis(fn, new, who):
    m = AXIS_RE.search(fn)
    if not m:
        sys.exit(f'  [{who}] bloc AXIS introuvable — moteur a change, patch a reviser')
    return fn[:m.start()] + new + fn[m.end():]


def retitle(fn, new_title, who):
    if OLD_TITLE not in fn:
        sys.exit(f'  [{who}] titre "{OLD_TITLE}" introuvable')
    return fn.replace(OLD_TITLE, new_title, 1)


def resuffix(fn, suffix):
    """ids DOM + global window uniques par chart."""
    fn = fn.replace('__tbChartPac', '__tbChartPac' + suffix)
    for dom in ('chart-svg-pac', 'chart-tooltip-pac', 'chart-legend-pac'):
        fn = fn.replace(dom, dom + suffix.lower())
    return fn


def add_fetch_cache(fn, who):
    if 'pacv2CachedFetch' in fn:
        print(f'  [{who}] cache fetch deja present')
        return fn
    if HELPER_ANCHOR not in fn or (FETCH_OLD not in fn and FETCH_OLD2 not in fn):
        print(f'  [{who}] ATTENTION anchors fetch introuvables, cache non injecte')
        return fn
    fn = fn.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    if FETCH_OLD in fn:
        fn = fn.replace(FETCH_OLD, FETCH_NEW, 1)
    else:
        fn = fn.replace(FETCH_OLD2, FETCH_NEW2, 1)
    return fn


def get_fn(w):
    return w['config']['settings']['markdownTextFunction']


def set_fn(w, fn):
    w['config']['settings']['markdownTextFunction'] = fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--offline', default=None, metavar='BACKUP_JSON',
                    help='transforme un backup local (preview), aucun acces reseau')
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')

    t = None
    if args.offline:
        with open(args.offline, encoding='utf-8') as f:
            dash = json.load(f)
        print(f'[offline] source: {args.offline}')
    else:
        t = os.environ.get('TB_TOKEN')
        if not t:
            if not args.pwd:
                sys.exit('Fournir --pwd, definir TB_TOKEN, ou utiliser --offline <backup>')
            t = login(args.user, args.pwd)
        dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
        bak = os.path.join(here, f'backup-mes-installations.before_pac_split.{ts}.json')
        with open(bak, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'backup: {bak}')

    conf = dash['configuration']
    widgets = conf['widgets']
    lay = conf['states'][STATE_ID]['layouts']['main']['widgets']

    if WID_PRESS in widgets or MARKER in get_fn(widgets[WID_PAC_CHART]):
        sys.exit('Deja applique (widget 0601 ou marker present). Rien a faire.')

    pac_orig = copy.deepcopy(widgets[WID_PAC_CHART])

    def make_dup(new_id, suffix, title, series, axis, cfg_title):
        w = copy.deepcopy(pac_orig)
        w['id'] = new_id
        w['config']['title'] = cfg_title
        fn = get_fn(w)
        fn = replace_series(fn, series, cfg_title)
        if axis:
            fn = replace_axis(fn, axis, cfg_title)
        fn = retitle(fn, title, cfg_title)
        fn = resuffix(fn, suffix)
        fn = add_fetch_cache(fn, cfg_title)
        set_fn(w, fn)
        widgets[new_id] = w
        print(f'  [+] {cfg_title} ({new_id[:13]}...)')

    # 1. Pressions HP/BP
    make_dup(WID_PRESS, 'Press', 'Pressions HP / BP', S_PRESS, A_PRESS, 'PAC Chart Pressions')
    # 3. Cycle frigorifique
    make_dup(WID_FRIG, 'Frig', 'Cycle frigorifique', S_FRIG, None, 'PAC Chart Frigo')
    # 4. Compresseur / detendeur
    make_dup(WID_COMP, 'Comp', 'Compresseur / Détendeur', S_COMP, None, 'PAC Chart Compresseur')
    # 5. Chaudiere bruleur / hydraulique (duplique du moteur PAC, series boil_*)
    make_dup(WID_BOIL2, 'Boil2', 'Brûleur / Circuit eau', S_BOIL2, A_BOIL2, 'Chaudière Chart Brûleur')

    # 2. widget PAC Chart existant -> Temperatures
    w = widgets[WID_PAC_CHART]
    fn = get_fn(w)
    fn = replace_series(fn, S_TEMP, 'PAC Chart')
    fn = retitle(fn, 'Températures', 'PAC Chart')
    fn = add_fetch_cache(fn, 'PAC Chart')
    set_fn(w, fn)
    w['config']['title'] = 'PAC Chart Températures'
    print('  [~] PAC Chart reutilise -> Temperatures')

    # chart chaudiere existant : cache fetch aussi (si moteur compatible)
    bw = widgets[WID_BOIL_CHART]
    set_fn(bw, add_fetch_cache(get_fn(bw), 'Chaudiere Chart'))

    # --- layout : grille 2x2 PAC + 2 charts chaudiere cote a cote ----------
    def place(wid, col, row, sx, sy, mo, mh=8):
        lay[wid] = dict(lay.get(wid, {}), col=col, row=row, sizeX=sx, sizeY=sy,
                        mobileOrder=mo, mobileHeight=mh)

    place(WID_PRESS,     0, 8.5,  12, 8, 4)
    place(WID_PAC_CHART, 12, 8.5, 12, 8, 4.2)
    place(WID_FRIG,      0, 16.5, 12, 8, 4.4)
    place(WID_COMP,      12, 16.5, 12, 8, 4.6)
    lay[WID_BOIL_INFO]['row'] = 24.5
    place(WID_BOIL_CHART, 0, 30.5, 12, 8, 6)
    place(WID_BOIL2,     12, 30.5, 12, 8, 6.5)
    lay[WID_PIE]['row'] = 38.5
    print('  [layout] PAC 2x2 (rows 8.5/16.5), chaudiere 2x1 (row 30.5), info 24.5, pie 38.5')

    if args.offline or args.dry_run:
        prev = os.path.join(here, f'backup-mes-installations.preview_pac_split.{ts}.json')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

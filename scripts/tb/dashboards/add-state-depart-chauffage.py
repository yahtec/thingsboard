#!/usr/bin/env python3
"""
Ajoute le state 'depart_chauffage' au dashboard "Mes Installations".

Contenu du nouveau state (meme techno que donnees_HP1) :
  1. "Chauffage Info"  : derive du widget PAC Info live (shim pac_v2 + retroview
     + picker TBV conserves) ; le corps devient un tableau calorimetre chauffage
     (heat.calo.* : pwr, hKwh, cKwh, qe, qeTot, tIn, tRet + variantes *U).
  2. "Timeline"        : duplication du widget Timeline (memes cles sessionStorage
     tduo.timeline.* / tduo.retroview.* -> boutons 4/8/12/24h + zoom partages).
  3. "Chauffage Chart" : derive du widget PAC Chart live (SVG custom, fetch pac_v2
     + PACV2_TO_SERIES, evt markers, retroview) avec 3 series :
     consigne (heat_setpoint), T depart (heat_tOut), T retour (heat_tIn).

Et rend la carte "Module Chauffage" de l'etat Unite (default) cliquable ->
goState('depart_chauffage') avec propagation entityId (meme mecanique pac-bloc).

NB : le bouton Retour de la navbar unifiee vit dans le fork ui-ngx
(home.component.ts) — patch separe + rebuild/deploy.

Idempotent : marker __HEAT_STATE_V1__ (state) et __HEATNAV_V1__ (carte Unite).

Usage:
  add-state-depart-chauffage.py --pwd <pwd> [--dry-run]
  TB_TOKEN=... add-state-depart-chauffage.py [--dry-run]
"""

import argparse, copy, json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'

# Widgets sources (live)
WID_PAC_INFO  = '49e69aac-15bc-32c4-c32d-c474cfeffa82'
WID_PAC_CHART = 'a1b2c3d4-0001-4000-a000-000000000001'
WID_TIMELINE  = 'a1b2c3d4-0400-4000-a000-000000000001'
WID_UNITE     = 'a1b2c3d4-d600-4000-a000-000000000001'   # "Donnees generales" (etat default)

# Nouveaux widgets
WID_HEAT_INFO  = 'a1b2c3d4-0500-4000-a000-000000000001'
WID_HEAT_CHART = 'a1b2c3d4-0501-4000-a000-000000000001'
WID_TIMELINE2  = 'a1b2c3d4-0400-4000-a000-000000000002'

STATE_ID = 'depart_chauffage'

MARKER_STATE  = '__HEAT_STATE_V1__'
MARKER_UNITE  = '__HEATNAV_V1__'


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}',
        headers={'X-Authorization': f'Bearer {t}'}, method='GET')
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


def must_replace(s, old, new, label, count=1):
    n = s.count(old)
    if n < count:
        sys.exit(f'[{label}] anchor introuvable ({n}/{count}) : {old[:80]!r}')
    return s.replace(old, new, count)


def replace_between(s, start, end, new, label):
    i = s.find(start)
    if i < 0:
        sys.exit(f'[{label}] start anchor introuvable : {start[:80]!r}')
    j = s.find(end, i)
    if j < 0:
        sys.exit(f'[{label}] end anchor introuvable : {end[:80]!r}')
    return s[:i] + new + s[j:]


# ---------------------------------------------------------------- Chauffage Info

HEAT_INFO_BODY = """html += '<div class="pac-detail-frame">';
html += '<div class="frame-header">';
var _entName = (data[0] && data[0].entityName) || '';
html += '<h2 class="pac-hybride-title">Départ chauffage</h2>';
if (_entName) html += '<div class="frame-install-sub">N° '+_entName+'</div>';
html += '<div class="frame-date" id="frame-date-val">'+(e['date']||'')+' '+(e['time']||'')+'</div>';
html += '</div>';

// Tableau calorimetre chauffage (heat.calo.* aplati en heat_calo_*)
function caloRow(label, val, unit, uVal) {
    var u = (uVal === null || uVal === undefined || uVal === '') ? '' : 'u:' + uVal;
    return '<tr><td class="calo-label">' + label + '</td>' +
           '<td class="calo-value">' + fv(val, unit || '', 1) + '</td>' +
           '<td class="calo-unit">' + u + '</td></tr>';
}
html += '<div class="calo-block">';
html += '<div class="calo-title">Calorimètre chauffage</div>';
html += '<table class="calo-table"><tbody>';
html += caloRow('Puissance', e['heat_calo_pwr'], '', e['heat_calo_pwrU']);
html += caloRow('Énergie chauffage', e['heat_calo_hKwh'], '', e['heat_calo_hKwhU']);
html += caloRow('Énergie refroidissement', e['heat_calo_cKwh'], '', e['heat_calo_cKwhU']);
html += caloRow('Débit', e['heat_calo_qe'], '', e['heat_calo_qeU']);
html += caloRow('Volume total', e['heat_calo_qeTot'], '', e['heat_calo_qeTotU']);
html += caloRow('T° aller', e['heat_calo_tIn'], ' °C');
html += caloRow('T° retour', e['heat_calo_tRet'], ' °C');
html += '</tbody></table></div>';

html += '</div>';
html += '</div>';

"""

HEAT_INFO_CSS_EXTRA = """
/* __HEAT_CALO_CSS__ */
.calo-block { max-width: 640px; margin: 10px auto 4px; padding: 0 8px; }
.calo-title { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; color: #c62828; margin-bottom: 6px; }
.calo-table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.calo-table td { padding: 7px 12px; border-bottom: 1px solid #eee; font-size: 13px; }
.calo-table tr:last-child td { border-bottom: none; }
.calo-label { color: #555; }
.calo-value { text-align: right; font-weight: 600; color: #222; font-variant-numeric: tabular-nums; }
.calo-unit { color: #999; font-size: 11px; text-align: right; white-space: nowrap; width: 60px; }
"""


def build_heat_info(widgets):
    w = copy.deepcopy(widgets[WID_PAC_INFO])
    c = w['config']
    fn = c['settings']['markdownTextFunction']
    fn = f'// {MARKER_STATE} Chauffage Info (derive de PAC Info)\n' + fn
    fn = replace_between(
        fn,
        "html += '<div class=\"pac-detail-frame\">';",
        '// Reecrit le bandeau TB',
        HEAT_INFO_BODY,
        'heat-info body')
    fn = must_replace(
        fn,
        "updateStateBanner('Données détaillées PAC ' + idx);",
        "// banner TB : nom du state deja correct ('Départ chauffage')",
        'heat-info banner')
    c['settings']['markdownTextFunction'] = fn
    c['settings']['markdownCss'] = c['settings'].get('markdownCss', '') + HEAT_INFO_CSS_EXTRA
    c['title'] = 'Chauffage Info'
    w['id'] = WID_HEAT_INFO
    return w


# ---------------------------------------------------------------- Chauffage Chart

HEAT_SERIES = """var SERIES = [
        { key: 'heat_setpoint', label: 'Consigne départ',     color: '#7cb342', axis: 'left', unit: '°C' },
        { key: 'heat_tOut',     label: 'T° départ chauffage', color: '#ef5350', axis: 'left', unit: '°C' },
        { key: 'heat_tIn',      label: 'T° retour chauffage', color: '#42a5f5', axis: 'left', unit: '°C' }
    ];"""


def build_heat_chart(widgets):
    w = copy.deepcopy(widgets[WID_PAC_CHART])
    c = w['config']
    fn = c['settings']['markdownTextFunction']
    fn = f'// {MARKER_STATE} Chauffage Chart (derive de PAC Chart)\n' + fn

    # SERIES : remplace le bloc complet
    i = fn.find('var SERIES = [')
    if i < 0:
        sys.exit('[heat-chart] anchor "var SERIES = [" introuvable')
    j = fn.find('];', i)
    if j < 0:
        sys.exit('[heat-chart] fin du bloc SERIES introuvable')
    fn = fn[:i] + HEAT_SERIES + fn[j + 2:]

    fn = must_replace(fn, 'Courbes PAC (24 heures)', 'Courbes Chauffage', 'heat-chart title')
    # Plage Y chauffage : 0..90 degC (au lieu de -30..90 pour la PAC)
    fn = must_replace(fn,
        "left: { min: -30, max: 90,",
        "left: { min: 0, max: 90,",
        'heat-chart axis')
    # Ids DOM + etat global distincts pour cohabiter avec le chart PAC
    for old, new in [('chart-svg-pac', 'chart-svg-heat'),
                     ('chart-tooltip-pac', 'chart-tooltip-heat'),
                     ('chart-legend-pac', 'chart-legend-heat'),
                     ('__tbChartPac', '__tbChartHeat')]:
        if old not in fn:
            sys.exit(f'[heat-chart] anchor {old!r} introuvable')
        fn = fn.replace(old, new)

    c['settings']['markdownTextFunction'] = fn
    c['title'] = 'Chauffage Chart'
    w['id'] = WID_HEAT_CHART
    return w


def build_timeline(widgets):
    w = copy.deepcopy(widgets[WID_TIMELINE])
    w['id'] = WID_TIMELINE2
    return w


# ---------------------------------------------------------------- Carte Unite cliquable

UNITE_CSS_EXTRA = """
/* __HEATNAV_CSS__ */
.heat-bloc { cursor: pointer; transition: box-shadow 0.2s, transform 0.15s; -webkit-tap-highlight-color: rgba(198, 40, 40, 0.15); }
.heat-bloc:hover { box-shadow: 0 4px 16px rgba(198, 40, 40, 0.25); transform: translateY(-2px); }
.heat-bloc:active { transform: translateY(0); box-shadow: 0 1px 4px rgba(198, 40, 40, 0.35); }
.heat-bloc:focus-visible { outline: 2px solid #c62828; outline-offset: 2px; }
.heat-bloc .detail-link { color: #c62828; }
"""


def patch_unite(widgets):
    w = widgets[WID_UNITE]
    c = w['config']
    fn = c['settings']['markdownTextFunction']
    if MARKER_UNITE in fn:
        print('  [unite] deja patche (skip idempotent)')
        return
    fn = f'// {MARKER_UNITE}\n' + fn
    fn = must_replace(
        fn,
        "h += '<div class=\"bloc heat-bloc\">';",
        "h += '<div class=\"bloc heat-bloc\" data-heatnav=\"1\" role=\"button\" tabindex=\"0\" aria-label=\"Voir départ chauffage\">';",
        'unite heat-bloc open')
    fn = must_replace(
        fn,
        "h += row('Position V3V', fv(e['heat_posV3V'], ' %'));\n    h += '</div></div>';",
        "h += row('Position V3V', fv(e['heat_posV3V'], ' %'));\n"
        "    h += '<div class=\"detail-link\">Voir détails →</div>';\n"
        "    h += '</div></div>';",
        'unite heat-bloc link')
    fn = must_replace(
        fn,
        "        var bloc = t.closest('.pac-bloc[data-hp]');",
        "        var hb = t.closest('.heat-bloc[data-heatnav]');\n"
        "        if (hb) { ev.preventDefault(); goState('depart_chauffage'); return; }\n"
        "        var bloc = t.closest('.pac-bloc[data-hp]');",
        'unite click handler')
    fn = must_replace(
        fn,
        "        if (t.classList.contains('pac-bloc')) {",
        "        if (t.classList.contains('heat-bloc')) { ev.preventDefault(); goState('depart_chauffage'); return; }\n"
        "        if (t.classList.contains('pac-bloc')) {",
        'unite keydown handler')
    c['settings']['markdownTextFunction'] = fn
    c['settings']['markdownCss'] = c['settings'].get('markdownCss', '') + UNITE_CSS_EXTRA
    print('  [unite] carte Module Chauffage rendue cliquable')


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = os.environ.get('TB_TOKEN')
    if not t:
        if not args.pwd:
            sys.exit('Fournir --pwd ou definir TB_TOKEN')
        t = login(args.user, args.pwd)

    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    conf = dash['configuration']
    widgets = conf['widgets']
    states = conf['states']

    # Backup local avant modification
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'backup-mes-installations.before_heat_state.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    changed = False

    if STATE_ID in states:
        print(f'  [state] {STATE_ID} existe deja (skip idempotent)')
    else:
        for src in (WID_PAC_INFO, WID_PAC_CHART, WID_TIMELINE, WID_UNITE):
            if src not in widgets:
                sys.exit(f'widget source absent du dashboard : {src}')
        widgets[WID_HEAT_INFO]  = build_heat_info(widgets)
        widgets[WID_HEAT_CHART] = build_heat_chart(widgets)
        widgets[WID_TIMELINE2]  = build_timeline(widgets)

        grid = copy.deepcopy(states['donnees_HP1']['layouts']['main'].get('gridSettings', {}))
        states[STATE_ID] = {
            'name': 'Départ chauffage',
            'root': False,
            'layouts': {'main': {
                # Timeline en haut, puis tableau calorimetre a gauche / courbes a droite (meme hauteur)
                'widgets': {
                    WID_TIMELINE2:  {'col': 0, 'row': 0,   'sizeX': 24, 'sizeY': 1.5, 'mobileOrder': 2, 'mobileHeight': 2},
                    WID_HEAT_INFO:  {'col': 0, 'row': 1.5, 'sizeX': 8,  'sizeY': 8,   'mobileOrder': 1, 'mobileHeight': 8},
                    WID_HEAT_CHART: {'col': 8, 'row': 1.5, 'sizeX': 16, 'sizeY': 8,   'mobileOrder': 3, 'mobileHeight': 8},
                },
                'gridSettings': grid,
            }},
        }
        print(f'  [state] {STATE_ID} cree (3 widgets)')
        changed = True

    fn_unite = widgets[WID_UNITE]['config']['settings']['markdownTextFunction']
    if MARKER_UNITE not in fn_unite:
        patch_unite(widgets)
        changed = True
    else:
        print('  [unite] deja patche (skip idempotent)')

    if not changed:
        print('Rien a faire.')
        return

    if args.dry_run:
        prev = bak.replace('.before_heat_state.', '.preview_heat_state.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

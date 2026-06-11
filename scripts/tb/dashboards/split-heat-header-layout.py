#!/usr/bin/env python3
"""
Rework layout du state 'depart_chauffage' (feedback user 2026-06-10) :

  Ligne 1 (pleine largeur) : bandeau "Départ chauffage" + n° série + date/heure
                             + bouton Rétroview (nouveau widget Chauffage Header).
  Ligne 2+ : gauche  = tableau calorimètre seul (widget Chauffage Info allégé)
             droite  = ligne Fenêtre (Timeline) puis Courbes Chauffage.
  Hauteur tableau (9.5) = timeline (1.5) + courbes (8).

Le widget Chauffage Header est dérivé du Chauffage Info live (conserve shim
pac_v2 + retroview + picker TBV) ; le Chauffage Info restant ne garde que le
tableau (shim données conservé pour suivre la rétroview).

Idempotent : skip si le widget header existe déjà.

Usage:
  split-heat-header-layout.py --pwd <pwd> [--dry-run]
"""

import argparse, copy, json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'

WID_INFO   = 'a1b2c3d4-0500-4000-a000-000000000001'  # Chauffage Info (header+table aujourd'hui)
WID_CHART  = 'a1b2c3d4-0501-4000-a000-000000000001'
WID_TL     = 'a1b2c3d4-0400-4000-a000-000000000002'
WID_HEADER = 'a1b2c3d4-0502-4000-a000-000000000001'  # nouveau bandeau

STATE_ID = 'depart_chauffage'


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


def cut_between(s, start, end, label, keep_end=True):
    """Supprime [start, end) ou [start, end] selon keep_end."""
    i = s.find(start)
    if i < 0:
        sys.exit(f'[{label}] start anchor introuvable : {start[:70]!r}')
    j = s.find(end, i)
    if j < 0:
        sys.exit(f'[{label}] end anchor introuvable : {end[:70]!r}')
    if not keep_end:
        j += len(end)
    return s[:i] + s[j:]


ANCHOR_CALO_START = "// Tableau calorimetre chauffage"
ANCHOR_CALO_END   = "html += '</tbody></table></div>';"
ANCHOR_NAV_START  = "html += '<nav class=\"md-nav\">';"
ANCHOR_NAV_END    = "html += '</nav>';"
ANCHOR_HDR_START  = "html += '<div class=\"frame-header\">';"
ANCHOR_TBV_START  = "    setTimeout(function(){"


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

    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'backup-mes-installations.before_heat_split.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    if WID_HEADER in widgets:
        print('deja patche (header widget existe) — rien a faire')
        return

    info = widgets[WID_INFO]
    fn = info['config']['settings']['markdownTextFunction']
    for a in (ANCHOR_CALO_START, ANCHOR_CALO_END, ANCHOR_NAV_START, ANCHOR_HDR_START, ANCHOR_TBV_START):
        if a not in fn:
            sys.exit(f'anchor absent du widget Chauffage Info : {a[:60]!r}')

    # --- Widget bandeau : Chauffage Info sans le tableau ----------------------
    header = copy.deepcopy(info)
    hfn = cut_between(fn, ANCHOR_CALO_START, ANCHOR_CALO_END, 'header/strip-table', keep_end=False)
    header['config']['settings']['markdownTextFunction'] = hfn
    header['config']['title'] = 'Chauffage Header'
    header['id'] = WID_HEADER
    widgets[WID_HEADER] = header

    # --- Widget tableau : Chauffage Info sans nav retroview, sans frame-header,
    #     sans bloc TBV (le picker/bouton vivent dans le bandeau) ---------------
    tfn = cut_between(fn, ANCHOR_NAV_START, ANCHOR_NAV_END, 'table/strip-nav', keep_end=False)
    tfn = cut_between(tfn, ANCHOR_HDR_START, ANCHOR_CALO_START, 'table/strip-header')
    tfn = cut_between(tfn, ANCHOR_TBV_START, 'return html;', 'table/strip-tbv')
    info['config']['settings']['markdownTextFunction'] = tfn
    # Le tableau occupe toute la carte (plus de centrage 640px)
    info['config']['settings']['markdownCss'] = info['config']['settings'].get('markdownCss', '') + \
        '\n/* __HEAT_SPLIT_CSS__ */\n.calo-block { max-width: none; margin: 4px 0 0; padding: 0 4px; }\n'

    # --- Layout : bandeau pleine largeur, tableau gauche, fenetre+courbes droite
    lay = conf['states'][STATE_ID]['layouts']['main']
    lay['widgets'] = {
        WID_HEADER: {'col': 0, 'row': 0,   'sizeX': 24, 'sizeY': 2,   'mobileOrder': 1, 'mobileHeight': 3},
        # table 6 cols + 1 col d'ecart, timeline/courbes 17 cols (feedback user)
        WID_INFO:   {'col': 0, 'row': 2,   'sizeX': 6,  'sizeY': 9.5, 'mobileOrder': 2, 'mobileHeight': 7},
        WID_TL:     {'col': 7, 'row': 2,   'sizeX': 17, 'sizeY': 1.5, 'mobileOrder': 3, 'mobileHeight': 2},
        WID_CHART:  {'col': 7, 'row': 3.5, 'sizeX': 17, 'sizeY': 8,   'mobileOrder': 4, 'mobileHeight': 8},
    }
    print('split + layout reorganise (header 24 / table 8 | timeline+chart 16)')

    if args.dry_run:
        prev = bak.replace('.before_heat_split.', '.preview_heat_split.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

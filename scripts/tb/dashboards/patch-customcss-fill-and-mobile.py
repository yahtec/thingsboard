#!/usr/bin/env python3
"""
configuration.settings.customCss (global dashboard) — 3 correctifs
(feedback user 2026-06-11) ajoutes en fin de customCss, markers idempotents :

A. desktop-card-fill : les cartes markdown (charts) ne remplissaient pas leur
   cellule (gris en bas) car l'hote <tb-markdown> est height:auto -> la chaine
   height:100% casse. Force tb-markdown/.tb-markdown-view a 100% en >=901px.
   (En mobile les blocs existants remettent height:auto, intacts.)

B. mobile-map-lock : le widget system.map (Leaflet) n'expose aucun reglage
   pour bloquer le drag tactile. touch-action:pan-y laisse le scroll vertical
   de page passer au lieu de deplacer la carte. (Si Leaflet ignore, prevoir
   un changement fork leaflet-gesture-handling + rebuild.)

C. mobile-scroll-fix : la carte 'Donnees generales' impose overflow-y:auto au
   niveau widget (double scrollbar). Override plus specifique pour rendre la
   page scrollable d'un seul tenant.

Idempotent via marker __CSS_FILL_MOBILE_V1__.

Usage:
  patch-customcss-fill-and-mobile.py --pwd <pwd> [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
MARKER       = '__CSS_FILL_MOBILE_V1__'

CSS_BLOCK = """

/* === __MARKER__ === */

/* A. desktop-card-fill : l'hote tb-markdown est height:auto par defaut, ce qui
   casse la chaine height:100% des charts et laisse une bande grise sous la
   carte. On force le remplissage uniquement en desktop ; les blocs mobile
   (max-width:900px) ci-dessus remettent height:auto et gardent la priorite. */
@media (min-width: 901px) {
    tb-markdown, .tb-markdown-view { height: 100% !important; }
}

/* B. mobile-map-lock : laisse le scroll vertical de page traverser la carte
   Leaflet au lieu de la deplacer (pas de reglage natif pour desactiver le
   drag sur system.map). */
@media (max-width: 900px) {
    .leaflet-container, tb-map, .tb-map, .tb-map-container {
        touch-action: pan-y !important;
    }
}

/* C. mobile-scroll-fix : tue la scrollbar interne de la carte markdown qui se
   superpose au scroll de page. Selecteur ancetre + tb-markdown pour battre le
   overflow-y:auto !important pose au niveau widget. */
@media (max-width: 900px) {
    .tb-dashboard-page tb-markdown .tb-markdown-view,
    .tb-dashboard-page .tb-markdown-view,
    tb-dashboard tb-markdown .tb-markdown-view {
        overflow: visible !important;
        overflow-y: visible !important;
    }
}
""".replace('__MARKER__', MARKER)


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
    settings = dash['configuration']['settings']

    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(here, f'backup-mes-installations.before_css_fill_mobile.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    css = settings.get('customCss', '')
    if MARKER in css:
        sys.exit('Deja applique (marker present). Rien a faire.')

    settings['customCss'] = css + CSS_BLOCK
    print(f'  customCss {len(css)} -> {len(settings["customCss"])} chars (+3 blocs)')

    if args.dry_run:
        prev = bak.replace('.before_css_fill_mobile.', '.preview_css_fill_mobile.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

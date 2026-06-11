#!/usr/bin/env python3
"""
State 'depart_chauffage' — 2 retouches (feedback user 2026-06-10) :

1. Ecart entre tableau calorimetre et colonne timeline/courbes reduit de 60%
   (1 colonne -> 0.4 : timeline+chart passent col 7->6.4, sizeX 17->17.6).
2. Tableau calorimetre : decode les codes d'unite Modbus du compteur Mainone
   (doc "Ultrasonic heat meter ModBus protocol V0.7") au lieu d'afficher u:N.
     0x0B3B = L/h          (debit instantane)
     0x0B2C = x10 W        (puissance)
     0x0C14 = x0,01 m3     (volume cumule)   0x0C15 = x0,1 m3
     0x0C06 = kWh          (energie)         0x0C07 = x10 kWh
   Le code peut arriver en decimal (3093) ou en notation hex; fallback
   affichage u:0xNNNN si code inconnu, rien si 0/absent.

Idempotent via marker __CALO_UNITS_V1__.

Usage:
  patch-calo-units-and-gap.py --pwd <pwd> [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'

WID_INFO  = 'a1b2c3d4-0500-4000-a000-000000000001'
WID_TL    = 'a1b2c3d4-0400-4000-a000-000000000002'
WID_CHART = 'a1b2c3d4-0501-4000-a000-000000000001'
STATE_ID  = 'depart_chauffage'
MARKER    = '__CALO_UNITS_V1__'

OLD_CALOROW = """function caloRow(label, val, unit, uVal) {
    var u = (uVal === null || uVal === undefined || uVal === '') ? '' : 'u:' + uVal;
    return '<tr><td class="calo-label">' + label + '</td>' +
           '<td class="calo-value">' + fv(val, unit || '', 1) + '</td>' +
           '<td class="calo-unit">' + u + '</td></tr>';
}"""

NEW_CALOROW = """// __CALO_UNITS_V1__ : codes unite Modbus Mainone (doc V0.7)
var CALO_UNITS = {
    2875: 'L/h',        // 0x0B3B debit instantane
    2860: 'x10 W',      // 0x0B2C puissance
    3092: 'x0,01 m\\u00b3', // 0x0C14 volume cumule
    3093: 'x0,1 m\\u00b3',  // 0x0C15 volume cumule (DN50+)
    3078: 'kWh',        // 0x0C06 energie
    3079: 'x10 kWh'     // 0x0C07 energie (DN50+)
};
function caloUnit(uVal) {
    if (uVal === null || uVal === undefined || uVal === '') return '';
    var n = Number(uVal);
    if (isNaN(n)) n = parseInt(String(uVal), 16);
    if (!n) return '';
    return CALO_UNITS[n] || ('u:0x' + n.toString(16).toUpperCase());
}
function caloRow(label, val, unit, uVal) {
    return '<tr><td class="calo-label">' + label + '</td>' +
           '<td class="calo-value">' + fv(val, unit || '', 1) + '</td>' +
           '<td class="calo-unit">' + caloUnit(uVal) + '</td></tr>';
}"""


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
    conf = dash['configuration']

    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'backup-mes-installations.before_calo_units.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    changed = False

    # 1. Ecart reduit de 60% (1 col -> 0.4)
    w = conf['states'][STATE_ID]['layouts']['main']['widgets']
    if w[WID_TL]['col'] != 6.4:
        w[WID_TL].update({'col': 6.4, 'sizeX': 17.6})
        w[WID_CHART].update({'col': 6.4, 'sizeX': 17.6})
        print('  [layout] ecart 1 -> 0.4 col (timeline/chart col 6.4, sizeX 17.6)')
        changed = True
    else:
        print('  [layout] deja applique')

    # 2. Decodage unites calorimetre
    info = conf['widgets'][WID_INFO]
    fn = info['config']['settings']['markdownTextFunction']
    if MARKER in fn:
        print('  [units] deja patche')
    elif OLD_CALOROW not in fn:
        sys.exit('  [units] anchor caloRow introuvable — fn a change, patch a reviser')
    else:
        info['config']['settings']['markdownTextFunction'] = fn.replace(OLD_CALOROW, NEW_CALOROW, 1)
        print('  [units] codes unite Mainone decodes dans le tableau')
        changed = True

    if not changed:
        print('Rien a faire.')
        return

    if args.dry_run:
        prev = bak.replace('.before_calo_units.', '.preview_calo_units.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

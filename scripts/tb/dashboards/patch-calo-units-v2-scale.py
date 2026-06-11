#!/usr/bin/env python3
"""
Tableau calorimetre (state depart_chauffage) — V2 du decodage d'unites :
applique le facteur d'echelle du code unite Mainone et affiche la valeur
convertie avec l'unite simple, au lieu de "66635 x0,01 m3".

  2875 (0x0B3B) -> x1    L/h     2860 (0x0B2C) -> x10   W
  3092 (0x0C14) -> x0.01 m3      3093 (0x0C15) -> x0.1  m3
  3078 (0x0C06) -> x1    kWh     3079 (0x0C07) -> x10   kWh

Valide sur 1res vraies donnees calorimetre St Leu 2026-06-10 17:30
(qe=2835 u:2875 -> 2835 L/h ; qeTot=66635 u:3092 -> 666,35 m3 ;
 tIn/tRet deja en degC cote automate, pas de division necessaire).

Idempotent : remplace le bloc __CALO_UNITS_V1__ par __CALO_UNITS_V2__.

Usage:
  patch-calo-units-v2-scale.py --pwd <pwd> [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
WID_INFO     = 'a1b2c3d4-0500-4000-a000-000000000001'
MARKER_V1, MARKER_V2 = '__CALO_UNITS_V1__', '__CALO_UNITS_V2__'

OLD_BLOCK = """// __CALO_UNITS_V1__ : codes unite Modbus Mainone (doc V0.7)
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

NEW_BLOCK = """// __CALO_UNITS_V2__ : codes unite Modbus Mainone (doc V0.7), facteur applique
var CALO_UNITS = {
    2875: { m: 1,    u: 'L/h', d: 0 },   // 0x0B3B debit instantane
    2860: { m: 10,   u: 'W',   d: 0 },   // 0x0B2C puissance (x10 W)
    3092: { m: 0.01, u: 'm\\u00b3',  d: 2 },  // 0x0C14 volume cumule (x0,01)
    3093: { m: 0.1,  u: 'm\\u00b3',  d: 1 },  // 0x0C15 volume cumule (x0,1 DN50+)
    3078: { m: 1,    u: 'kWh', d: 0 },   // 0x0C06 energie
    3079: { m: 10,   u: 'kWh', d: 0 }    // 0x0C07 energie (x10 DN50+)
};
function caloRow(label, val, unit, uVal) {
    var disp, udisp = '';
    var n = Number(uVal);
    if (isNaN(n)) n = parseInt(String(uVal), 16);
    var spec = n ? CALO_UNITS[n] : null;
    if (spec) {
        var v = parseFloat(val);
        disp = isBad(v) ? '--' : (v * spec.m).toFixed(spec.d);
        udisp = spec.u;
    } else {
        disp = fv(val, unit || '', 1);
        if (n) udisp = 'u:0x' + n.toString(16).toUpperCase();
    }
    return '<tr><td class="calo-label">' + label + '</td>' +
           '<td class="calo-value">' + disp + '</td>' +
           '<td class="calo-unit">' + udisp + '</td></tr>';
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
    info = dash['configuration']['widgets'][WID_INFO]
    fn = info['config']['settings']['markdownTextFunction']

    if MARKER_V2 in fn:
        print('deja patche (V2) — rien a faire')
        return
    if OLD_BLOCK not in fn:
        sys.exit('bloc V1 introuvable — fn a change, patch a reviser')

    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'backup-mes-installations.before_calo_v2.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    info['config']['settings']['markdownTextFunction'] = fn.replace(OLD_BLOCK, NEW_BLOCK, 1)

    if args.dry_run:
        print('[dry-run] pas de POST.')
        return
    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

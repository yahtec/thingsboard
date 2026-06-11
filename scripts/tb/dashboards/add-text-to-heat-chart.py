#!/usr/bin/env python3
"""
State 'depart_chauffage' — ajoute la temperature exterieure (tExt, cle
top-level pac_v2, sans prefixe HPn_) au chart Chauffage.

L'axe gauche passe de 0..90 a -20..90 pour couvrir les tExt negatives.

Idempotent : skip si tExt deja dans SERIES.

Usage:
  add-text-to-heat-chart.py --pwd <pwd> [--dry-run]
"""

import argparse, json, os, re, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
WID_CHART    = 'a1b2c3d4-0501-4000-a000-000000000001'

OLD_SERIES = """var SERIES = [
        { key: 'heat_setpoint', label: 'Consigne départ',     color: '#7cb342', axis: 'left', unit: '°C' },
        { key: 'heat_tOut',     label: 'T° départ chauffage', color: '#ef5350', axis: 'left', unit: '°C' },
        { key: 'heat_tIn',      label: 'T° retour chauffage', color: '#42a5f5', axis: 'left', unit: '°C' }
    ];"""

NEW_SERIES = """var SERIES = [
        { key: 'heat_setpoint', label: 'Consigne départ',     color: '#7cb342', axis: 'left', unit: '°C' },
        { key: 'heat_tOut',     label: 'T° départ chauffage', color: '#ef5350', axis: 'left', unit: '°C' },
        { key: 'heat_tIn',      label: 'T° retour chauffage', color: '#42a5f5', axis: 'left', unit: '°C' },
        { key: 'tExt',          label: 'T° extérieure',       color: '#90a4ae', axis: 'left', unit: '°C' }
    ];"""

OLD_AXIS_LEFT = "left: { min: 0, max: 90,"
NEW_AXIS_LEFT = "left: { min: -20, max: 90,"


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

    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(here, f'backup-mes-installations.before_heat_text.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    w = conf['widgets'][WID_CHART]
    fn = w['config']['settings']['markdownTextFunction']

    if "key: 'tExt'" in fn:
        sys.exit('Deja applique (tExt present). Rien a faire.')
    if OLD_SERIES not in fn:
        sys.exit('Anchor SERIES introuvable — le chart a change, patch a reviser')
    if OLD_AXIS_LEFT not in fn:
        sys.exit('Anchor AXIS left introuvable — le chart a change, patch a reviser')

    fn = fn.replace(OLD_SERIES, NEW_SERIES, 1)
    fn = fn.replace(OLD_AXIS_LEFT, NEW_AXIS_LEFT, 1)
    w['config']['settings']['markdownTextFunction'] = fn
    print('  [series] tExt ajoutee, axe gauche -20..90')

    if args.dry_run:
        prev = bak.replace('.before_heat_text.', '.preview_heat_text.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

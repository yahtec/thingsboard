#!/usr/bin/env python3
"""
Ajoute le code defaut 114 'Defaut remplissage eau' a la table FAULT_LABELS
des deux widgets qui la portent :
  - tduo.events_history   (Historique evenements)
  - tduo.fault_diagnostic (Diagnostic defaut)

La table actuelle couvre 0..113 (index 114 = nouvelle entree firmware). Idempotent : skip si '114:' deja present.

Usage :
  python scripts/tb/widgets/patch-fault-labels-add-114.py --pwd <password>
  # ou avec un token existant :
  $env:TB_TOKEN = '<jwt>'; python scripts/tb/widgets/patch-fault-labels-add-114.py
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL = 'https://thingsboard.tsmart.fr'

WIDGETS = {
    'events_history':   'af86baf0-3fe1-11f1-bbfe-e1395562cba0',
    'fault_diagnostic': '5e6e2180-478e-11f1-a9c9-47ea18512754',
}

OLD_TAIL = "113:'Defaut temperature sortie chaudiere'};"
NEW_TAIL = "113:'Defaut temperature sortie chaudiere',114:'Defaut remplissage eau'};"


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o:
        return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def patch_widget(name, wid, t):
    w = http_get(f'/api/widgetType/{wid}', t)
    print(f'[{name}] {w["name"]} v{w.get("version", "?")}')
    cs = w['descriptor']['controllerScript']
    if "114:'Defaut remplissage eau'" in cs:
        print('  deja patche (skip idempotent)')
        return
    if OLD_TAIL not in cs:
        sys.exit(f'[{name}] pattern OLD_TAIL introuvable â€” la table a change, patch a reviser')
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = f'scripts/tb/backup/widgets-tduo-v1/{name}.before_fault114.{ts}.json'
    with open(bak, 'wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'  backup: {bak}')
    w['descriptor']['controllerScript'] = cs.replace(OLD_TAIL, NEW_TAIL, 1)
    resp = http_post('/api/widgetType', w, t)
    print(f'  OK, nouvelle version: {resp.get("version", "?")}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    args = ap.parse_args()
    t = os.environ.get('TB_TOKEN')
    if not t:
        if not args.pwd:
            sys.exit('Fournir --pwd ou definir TB_TOKEN')
        t = login(args.user, args.pwd)
    for name, wid in WIDGETS.items():
        patch_widget(name, wid, t)


if __name__ == '__main__':
    main()

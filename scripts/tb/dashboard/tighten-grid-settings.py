#!/usr/bin/env python3
"""
Reduit l'espace en haut des widgets (outerMargin=false) et active autoFillHeight
sur les states "single-widget" pour que la viewport soit remplie et le scroll
interne aux widgets fonctionne.
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'

# States avec single big widget : viewport rempli + scroll interne
SINGLE_WIDGET_STATES = {'menu', 'historique', 'fault_diagnostic', 'configuration', 'profil', 'notifications_admin'}


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
    t = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    print(f'Dashboard v{dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/dashboard/backup/mes-installations.tighten.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    for sid, st in dash['configuration']['states'].items():
        for lt in ('main',):
            gs = st.get('layouts', {}).get(lt, {}).get('gridSettings', {})
            if not gs: continue
            gs['outerMargin'] = False
            gs['margin'] = 0
            if sid in SINGLE_WIDGET_STATES:
                gs['autoFillHeight'] = True
                gs['mobileAutoFillHeight'] = True
            print(f'  {sid}: outerMargin=false margin=0 autoFillHeight={gs.get("autoFillHeight")}')

    resp = http_post('/api/dashboard', dash, t)
    print(f'\nPosted v{resp["version"]}')


if __name__ == '__main__': main()

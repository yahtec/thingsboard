#!/usr/bin/env python3
"""
Bascule le widget Map (1a5b4c03-ba38-...) du dashboard "Mes Installations"
de Google Maps (billing desactive) vers OpenStreetMap (gratuit, illimite).
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
MAP_WIDGET_ID = '1a5b4c03-ba38-ad06-5f7a-b82453a7807d'
BASE_URL     = 'https://thingsboard.tsmart.fr'


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
    with open(f'scripts/tb/dashboard/backup/mes-installations.osm.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    mp = dash['configuration']['widgets'].get(MAP_WIDGET_ID)
    if not mp: sys.exit('Map widget not found')
    settings = mp['config']['settings']
    layers = settings.get('layers', [])
    print(f'Current layers ({len(layers)}):')
    for l in layers:
        print(f'  - provider={l.get("provider")} type={l.get("layerType")} label={l.get("label")!r}')

    # Replace layers with OpenStreetMap Mapnik
    settings['layers'] = [{
        'label': 'OpenStreetMap',
        'provider': 'openstreet',
        'layerType': 'OpenStreetMap.Mapnik',
        'referenceLayer': None,
    }]
    print(f'\nNew layers:')
    for l in settings['layers']:
        print(f'  - provider={l["provider"]} type={l["layerType"]} label={l["label"]!r}')

    resp = http_post('/api/dashboard', dash, t)
    print(f'\nPosted v{resp["version"]}')


if __name__ == '__main__': main()

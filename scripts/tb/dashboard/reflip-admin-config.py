#!/usr/bin/env python3
"""Re-flip admin TBN-RESTRICT-ADMIN : retour comportement original.
   Configuration cachee par defaut, visible admin uniquement (partout).
"""
import argparse, json, sys, time, urllib.request, urllib.error, re

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
BASE_URL     = 'https://thingsboard.tsmart.fr'


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o: return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    with urllib.request.urlopen(r, timeout=300) as o: return json.loads(o.read().decode('utf-8'))

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
    nv = dash['configuration']['widgets'][NAVBAR_ID]
    css = nv['config']['settings']['cardCss']
    FLIPPED = '.md-nav .back-btn[data-navtarget="configuration"] { display:inline-flex; }\n.md-nav.tbn-is-admin .back-btn[data-navtarget="configuration"] { display:none; }'
    ORIGINAL = '.md-nav .back-btn[data-navtarget="configuration"] { display:none; }\n.md-nav.tbn-is-admin .back-btn[data-navtarget="configuration"] { display:inline-flex; }'
    if FLIPPED not in css:
        sys.exit(f'flipped pattern not found, manual review required')
    nv['config']['settings']['cardCss'] = css.replace(FLIPPED, ORIGINAL, 1)
    print(f'Re-flipped admin rule. Posting...')
    resp = http_post('/api/dashboard', dash, t)
    print(f'New version: {resp["version"]}')

if __name__ == '__main__': main()

#!/usr/bin/env python3
"""
Injection ponctuelle d'une RESOLUTION de defaut (evt_*) en flat sur un device PAC.

Contexte : suite a la regression Phase 3.6 (cut-flat-branch.py), les bundles evt_*
n'etaient plus persistes -> des resolutions edge ont ete perdues -> des apparitions
restent 'actif' dans events_history alors que le defaut est resolu.

Cet outil pose un bundle resolution coherent (evt_type=4 / evt_status=0) avec un
evt_id frais (epoch SECONDES) au ts courant, ce qui appariera l'apparition ouverte
(meme evt_fault + evt_device) cote widget events_history (_pair: openByKey[fault|dev]).

Convention verifiee en prod :
  apparition  = evt_type 1 / evt_status 1
  resolution  = evt_type 4 / evt_status 0

Usage:
  inject-evt-resolution.py --pwd <pwd> --entity-id <uuid> --fault 88 --device 50
"""

import argparse, json, sys, time, urllib.request, urllib.error
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo('Europe/Paris')
except Exception:
    PARIS = None

BASE_URL = 'https://thingsboard.tsmart.fr'


def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=60) as o:
            raw = o.read().decode('utf-8')
            return json.loads(raw) if raw.strip() else {}
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
    ap.add_argument('--entity-id', required=True, help='UUID du device PAC')
    ap.add_argument('--fault', type=int, required=True, help='code evt_fault (ex: 88)')
    ap.add_argument('--device', type=int, required=True, help='evt_device sous-equipement (ex: 50)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    now_ms = int(time.time() * 1000)
    now_s = now_ms // 1000
    dt = datetime.fromtimestamp(now_s, PARIS) if PARIS else datetime.fromtimestamp(now_s)
    values = {
        'evt_type': 4,
        'evt_status': 0,
        'evt_fault': args.fault,
        'evt_device': args.device,
        'evt_id': now_s,
        'evt_date': dt.strftime('%d/%m/%y'),
        'evt_time': dt.strftime('%H:%M:%S'),
    }
    payload = {'ts': now_ms, 'values': values}
    print('Resolution a injecter :')
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f'  -> DEVICE {args.entity_id}')
    if args.dry_run:
        print('DRY-RUN : rien envoye.')
        return

    token = login(args.user, args.pwd)
    http_post(f'/api/plugins/telemetry/DEVICE/{args.entity_id}/timeseries/ANY', payload, token)
    print('OK : resolution injectee (flat ts_kv).')


if __name__ == '__main__': main()

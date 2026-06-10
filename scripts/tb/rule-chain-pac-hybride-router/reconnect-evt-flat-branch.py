#!/usr/bin/env python3
"""
Fix regression Phase 3.6 : cut-flat-branch.py a orpheline 'save TS (per-id device)',
ce qui a aussi tue la persistance des bundles evt_* (POSTs ad-hoc, HPs absent).

Symptome : defauts (apparition/resolution) plus enregistres depuis ~06-08 ->
events_history fige, defauts comm restent 'actif' apres reconnexion PAC.

Fix chirurgical (preserve le gain de lignes de la Phase 3.6) :
  Connecter [Filter HPs present v2] --False--> [save TS (per-id device)]

  - Live cyclique (HPs present)  --True-->  ... --> Save TS pac_v2   (inchange)
  - Bundle evt_* (HPs absent)    --False--> save TS (per-id device)  (REPARE)

Le live ne repasse PAS par save TS (per-id device) -> pas de re-sauvegarde des
cles flat live redondantes -> economie Phase 3.6 intacte.

Idempotent : si la connexion False existe deja, ne refait rien.

Usage:
  reconnect-evt-flat-branch.py --pwd <pwd>
"""

import argparse, json, sys, time, os, urllib.request, urllib.error

RC_ID      = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL   = 'https://thingsboard.tsmart.fr'
FILTER_NODE = 'Filter HPs present v2'
SAVE_TS_NODE = 'save TS (per-id device)'
LINK_TYPE   = 'False'


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o: return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=120) as o: return json.loads(o.read().decode('utf-8'))
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

    token = login(args.user, args.pwd)
    meta = http_get(f'/api/ruleChain/{RC_ID}/metadata', token)
    nodes = meta['nodes']

    def idx(name):
        return next((i for i, n in enumerate(nodes) if n['name'] == name), None)

    filt_idx = idx(FILTER_NODE)
    save_idx = idx(SAVE_TS_NODE)
    if filt_idx is None: sys.exit(f'Node not found: {FILTER_NODE}')
    if save_idx is None: sys.exit(f'Node not found: {SAVE_TS_NODE}')
    print(f'Indices : "{FILTER_NODE}"={filt_idx}  "{SAVE_TS_NODE}"={save_idx}')

    # Backup
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup_path = f'scripts/tb/rule-chain-pac-hybride-router/backup/rule-chain-reconnect-evt-{ts}.json'
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    with open(backup_path, 'wb') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup  : {backup_path}')

    conns = meta['connections']
    exists = any(c['fromIndex'] == filt_idx and c['toIndex'] == save_idx and c['type'] == LINK_TYPE
                 for c in conns)
    if exists:
        print('Connexion False deja presente (idempotent skip)')
        return

    conns.append({'fromIndex': filt_idx, 'toIndex': save_idx, 'type': LINK_TYPE})
    print(f'Ajout connexion [{FILTER_NODE}] --{LINK_TYPE}--> [{SAVE_TS_NODE}]')
    print(f'Connections: {len(conns) - 1} -> {len(conns)}')

    result = http_post('/api/ruleChain/metadata', meta, token)
    print(f'\nRule chain mise a jour. Nodes={len(result.get("nodes", []))} '
          f'Connections={len(result.get("connections", []))}')


if __name__ == '__main__': main()

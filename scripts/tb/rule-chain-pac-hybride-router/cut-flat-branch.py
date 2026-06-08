#!/usr/bin/env python3
"""
Phase 3.6 : coupe la branche flat de la rule chain PAC Hybride Router.

Avant :
  [18] Assign --Success/Failure--> [3] save TS (per-id device) --Success--> [10] DeviceProfile
                                                              --Success--> [11] mark active
                                                              --Success--> [13] Filter HPs v2

Apres :
  [18] Assign --Success/Failure--> [10] DeviceProfile
                                   [11] mark active
                                   [13] Filter HPs v2
  [3] save TS (per-id device) reste en place mais ORPHELIN (no inbound)
    -> aucun message recu, jamais execute
    -> rollback facile : reconnecter les liens

Resultat : ~18 rows top-level (HPs/dhw/heat/caloM/pump1M/pump2M/tExt/etc.)
ne sont plus sauvees par sample. Le pac_v2 json_v en pac_v2 contient deja
toutes ces data. Gain : ~2.3M rows/mois sur ts_kv (3 devices × 1/min × 18 keys).

Idempotent : si les nouvelles connexions [18]->[10/11/13] existent deja,
ne refait rien.

Usage:
  cut-flat-branch.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

RC_ID    = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL = 'https://thingsboard.tsmart.fr'

SAVE_TS_NODE_NAME = 'save TS (per-id device)'
ASSIGN_NODE_NAME  = 'Assign to Yahtec'
DOWNSTREAM_NODES  = ['DeviceProfile (alarms)', 'mark active', 'Filter HPs present v2']


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
        return next((i for i,n in enumerate(nodes) if n['name']==name), None)

    save_ts_idx = idx(SAVE_TS_NODE_NAME)
    assign_idx  = idx(ASSIGN_NODE_NAME)
    downstream_idx = {name: idx(name) for name in DOWNSTREAM_NODES}

    if save_ts_idx is None: sys.exit(f'{SAVE_TS_NODE_NAME} not found')
    if assign_idx is None:  sys.exit(f'{ASSIGN_NODE_NAME} not found')
    for name, i in downstream_idx.items():
        if i is None: sys.exit(f'{name} not found')

    print(f'Indices : save TS={save_ts_idx} assign={assign_idx}')
    for name, i in downstream_idx.items():
        print(f'           {name}={i}')

    # Backup
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup_path = f'scripts/tb/rule-chain-pac-hybride-router/backup/rule-chain-phase36-{ts}.json'
    import os
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    with open(backup_path, 'wb') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup : {backup_path}')

    conns = meta['connections']
    before_count = len(conns)

    # 1. Retirer les connexions [18]->[3] et [3]->[10/11/13]
    new_conns = []
    removed = 0
    for c in conns:
        # [assign]->[save TS]
        if c['fromIndex']==assign_idx and c['toIndex']==save_ts_idx:
            removed += 1
            continue
        # [save TS]->[downstream]
        if c['fromIndex']==save_ts_idx and c['toIndex'] in downstream_idx.values():
            removed += 1
            continue
        new_conns.append(c)
    print(f'Removed {removed} connections involving save TS')

    # 2. Ajouter [18]->[downstream] pour Success + Failure
    added = 0
    for dest_idx in downstream_idx.values():
        for conn_type in ('Success', 'Failure'):
            new_conn = {'fromIndex': assign_idx, 'toIndex': dest_idx, 'type': conn_type}
            # Idempotent : check si existe deja
            if any(c['fromIndex']==assign_idx and c['toIndex']==dest_idx and c['type']==conn_type for c in new_conns):
                continue
            new_conns.append(new_conn)
            added += 1
    print(f'Added {added} connections [assign]->[downstream]')

    meta['connections'] = new_conns
    print(f'Connections: {before_count} -> {len(new_conns)}')

    if added == 0 and removed == 0:
        print('Nothing changed (already idempotent)')
        return

    result = http_post('/api/ruleChain/metadata', meta, token)
    print(f'\nRule chain updated. Nodes={len(result.get("nodes",[]))} Connections={len(result.get("connections",[]))}')


if __name__ == '__main__': main()

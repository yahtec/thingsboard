#!/usr/bin/env python3
"""
Ajoute un node 'Assign to Yahtec' (TbAssignToCustomerNode) dans la rule chain
PAC Hybride Router, entre 'originator -> device(${id})' et 'save TS (per-id device)'.

Effet : tout nouveau device cree via TbChangeOriginatorNode est auto-assigne
au customer Yahtec. Avant cette modif les anciens devices etaient assignes
manuellement via UI.

Idempotent : si un node 'Assign to Yahtec' existe deja, ne refait rien.

Usage:
  add-assign-customer-node.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

RC_ID    = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL = 'https://thingsboard.tsmart.fr'
NODE_NAME = 'Assign to Yahtec'
CUSTOMER_NAME = 'yahtec'


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
    print(f'Current rule chain : {len(nodes)} nodes')

    # Find indices we need
    orig_idx = None
    save_idx = None
    assign_idx = None
    for i, n in enumerate(nodes):
        if n['name'] == 'originator -> device(${id})':
            orig_idx = i
        elif n['name'] == 'save TS (per-id device)':
            save_idx = i
        elif n['name'] == NODE_NAME:
            assign_idx = i

    if orig_idx is None or save_idx is None:
        sys.exit(f'Required nodes not found (orig_idx={orig_idx}, save_idx={save_idx})')
    print(f'  originator -> device(${{id}}) at index {orig_idx}')
    print(f'  save TS (per-id device) at index {save_idx}')

    if assign_idx is not None:
        print(f'  "{NODE_NAME}" already exists at index {assign_idx} -- idempotent skip')
        return

    # Backup
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/backup/rule-chain-{ts}.json', 'wb') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'  Backup saved')

    # 1. Add new Assign to Yahtec node
    new_node = {
        'name': NODE_NAME,
        'type': 'org.thingsboard.rule.engine.action.TbAssignToCustomerNode',
        'configuration': {
            'customerNamePattern': CUSTOMER_NAME,
            'createCustomerIfNotExists': False,
        },
        'additionalInfo': {
            'layoutX': 400,
            'layoutY': 50,
            'description': 'Assigne le device au customer yahtec apres creation. Idempotent.',
        },
    }
    nodes.append(new_node)
    new_idx = len(nodes) - 1
    print(f'  Added "{NODE_NAME}" at index {new_idx}')

    # 2. Rewire connections
    # Existing : originator (orig_idx) --Success--> save TS (save_idx)
    # New      : originator --Success--> assign (new_idx) --Success+Failure--> save TS
    new_conns = []
    rewired = 0
    for c in meta['connections']:
        if c['fromIndex'] == orig_idx and c['toIndex'] == save_idx and c['type'] == 'Success':
            # Replace with originator --Success--> Assign
            new_conns.append({'fromIndex': orig_idx, 'toIndex': new_idx, 'type': 'Success'})
            rewired += 1
        else:
            new_conns.append(c)
    # Add new conns from Assign to save TS (both Success and Failure -- failure should still save data)
    new_conns.append({'fromIndex': new_idx, 'toIndex': save_idx, 'type': 'Success'})
    new_conns.append({'fromIndex': new_idx, 'toIndex': save_idx, 'type': 'Failure'})
    print(f'  Rewired {rewired} Success edge from originator')
    print(f'  Added Assign -> save TS (Success + Failure)')

    meta['connections'] = new_conns

    # POST
    result = http_post('/api/ruleChain/metadata', meta, token)
    print(f'  Rule chain updated. New nodes count: {len(result.get("nodes", []))}')


if __name__ == '__main__':
    main()

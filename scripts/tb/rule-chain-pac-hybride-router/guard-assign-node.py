#!/usr/bin/env python3
"""Insere un garde 'site_assigned' avant l'assign yahtec de la rule chain PAC Hybride Router.

Apres 'originator -> device(${id})' :
  -> [load site_assigned] (TbGetAttributesNode, server, tolere absence)
  -> [Provisionnee ?] (filtre) : ss_site_assigned == 'true' ?
       True  -> 'save TS (per-id device)'      (provisionnee : on ne reassigne pas)
       False -> 'Assign to Yahtec'              (nouvelle : zone d'attente)
Idempotent (skip si 'Provisionnee ?' existe). Dry-run par defaut ; --apply pour ecrire.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

RC_ID    = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL = os.environ.get('TB_BASE_URL', 'https://thingsboard.tsmart.fr')
ORIG, SAVE, ASSIGN = 'originator -> device(${id})', 'save TS (per-id device)', 'Assign to Yahtec'
GETATTR, FILTER = 'load site_assigned', 'Provisionnee ?'


def _req(method, p, t, body=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    h = {'X-Authorization': f'Bearer {t}'}
    if data is not None:
        h['Content-Type'] = 'application/json; charset=utf-8'
    return urllib.request.Request(f'{BASE_URL}{p}', data=data, headers=h, method=method)


def http_get(p, t):
    with urllib.request.urlopen(_req('GET', p, t), timeout=60) as o:
        return json.loads(o.read().decode('utf-8'))


def http_post(p, b, t):
    try:
        with urllib.request.urlopen(_req('POST', p, t, b), timeout=120) as o:
            raw = o.read().decode('utf-8')
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def token_or_login(user, pwd):
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if not pwd:
        sys.exit('Fournir --pwd ou definir TB_TOKEN')
    b = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    t = token_or_login(args.user, args.pwd)
    meta = http_get(f'/api/ruleChain/{RC_ID}/metadata', t)
    nodes, conns = meta['nodes'], meta['connections']
    idx = {n['name']: i for i, n in enumerate(nodes)}

    for req in (ORIG, SAVE, ASSIGN):
        if req not in idx:
            sys.exit(f'Node requis introuvable : {req!r}')
    if FILTER in idx:
        print(f'"{FILTER}" existe deja -> idempotent skip')
        return
    orig_i, save_i, assign_i = idx[ORIG], idx[SAVE], idx[ASSIGN]

    getattr_node = {
        'name': GETATTR,
        'type': 'org.thingsboard.rule.engine.metadata.TbGetAttributesNode',
        'configuration': {
            'fetchTo': 'METADATA',
            'clientAttributeNames': [], 'sharedAttributeNames': [],
            'serverAttributeNames': ['site_assigned'],
            'latestTsKeyNames': [],
            'tellFailureIfAbsent': False, 'getLatestValueWithTs': False,
        },
        'additionalInfo': {'layoutX': 520, 'layoutY': 260,
            'description': "Charge l'attribut serveur site_assigned -> metadata ss_site_assigned. Tolere l'absence."},
    }
    filter_node = {
        'name': FILTER,
        'type': 'org.thingsboard.rule.engine.filter.TbJsFilterNode',
        'configuration': {
            'scriptLang': 'JS',
            'jsScript': "return metadata.ss_site_assigned === 'true';",
            'tbelScript': "return metadata.ss_site_assigned == 'true';",
        },
        'additionalInfo': {'layoutX': 720, 'layoutY': 260,
            'description': "True=provisionnee (skip assign). False/absent=zone d'attente yahtec."},
    }
    nodes.append(getattr_node); getattr_i = len(nodes) - 1
    nodes.append(filter_node);  filter_i  = len(nodes) - 1

    new_conns = [c for c in conns
                 if not (c['fromIndex'] == orig_i and c['toIndex'] == assign_i and c['type'] == 'Success')]
    new_conns += [
        {'fromIndex': orig_i,    'toIndex': getattr_i, 'type': 'Success'},
        {'fromIndex': getattr_i, 'toIndex': filter_i,  'type': 'Success'},
        {'fromIndex': getattr_i, 'toIndex': filter_i,  'type': 'Failure'},
        {'fromIndex': filter_i,  'toIndex': save_i,     'type': 'True'},
        {'fromIndex': filter_i,  'toIndex': assign_i,   'type': 'False'},
    ]
    meta['connections'] = new_conns

    print(f'nodes: +2 ({GETATTR} @ {getattr_i}, {FILTER} @ {filter_i})')
    print(f'rewire: {ORIG} --Success--> {GETATTR} --> {FILTER} --True--> {SAVE} / --False--> {ASSIGN}')
    print(f'  drop 1 edge {ORIG} --Success--> {ASSIGN}')

    if not args.apply:
        print('\n[DRY-RUN] aucune ecriture. Ajouter --apply pour appliquer.')
        return

    ts = time.strftime('%Y%m%d-%H%M%S')
    bpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup', f'metadata.before_guard.{ts}.json')
    with open(bpath, 'wb') as f:
        f.write(json.dumps(http_get(f'/api/ruleChain/{RC_ID}/metadata', t), ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'backup: {bpath}')
    res = http_post('/api/ruleChain/metadata', meta, t)
    print(f'OK — rule chain a {len(res.get("nodes", []))} nodes')


if __name__ == '__main__':
    main()

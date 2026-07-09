#!/usr/bin/env python3
"""Insere un garde 'site_assigned' avant l'assign yahtec de la rule chain PAC Hybride Router.

Apres 'originator -> device(${id})' :
  -> [load site_assigned] (TbGetAttributesNode, server, tolere absence)
  -> [Provisionnee ?] (filtre) : ss_site_assigned == 'true' ?
       True  -> {Filter HPs present v2, mark active, DeviceProfile (alarms)}  (provisionnee :
                on ne reassigne pas, mais on REJOINT le pipeline normal = branche False MOINS l'assign)
       False -> 'Assign to Yahtec'                                            (nouvelle : zone d'attente)

La branche True ne doit JAMAIS finir sur un noeud de save brut (bug historique corrige :
c'etait 'save TS (per-id device)', une impasse qui figeait pac_v2 + coupait alarmes/mark active).
Ce script absorbe l'ancien patch fix-guard-true-branch.py.

Idempotent (skip si garde deja active). Reutilise les nodes orphelins. Dry-run par defaut ; --apply pour ecrire.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

RC_ID    = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL = os.environ.get('TB_BASE_URL', 'https://thingsboard.tsmart.fr')
ORIG, ASSIGN = 'originator -> device(${id})', 'Assign to Yahtec'
GETATTR, FILTER = 'load site_assigned', 'Provisionnee ?'
# Branche True = branche False MOINS l'assign : les memes cibles que 'Assign to Yahtec --Success-->'.
GOOD_TARGETS = ['Filter HPs present v2', 'mark active', 'DeviceProfile (alarms)']


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


def _getattr_node():
    return {
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


def _filter_node():
    return {
        'name': FILTER,
        'type': 'org.thingsboard.rule.engine.filter.TbJsFilterNode',
        'configuration': {
            'scriptLang': 'JS',
            'jsScript': "return metadata.ss_site_assigned === 'true';",
            'tbelScript': "return metadata.ss_site_assigned == 'true';",
        },
        'additionalInfo': {'layoutX': 720, 'layoutY': 260,
            'description': "True=provisionnee (rejoint le pipeline sans reassigner). False/absent=zone d'attente yahtec."},
    }


def apply_guard(meta):
    """Mute meta en place pour inserer/recabler la garde. Pure (aucun HTTP).

    - sys.exit(...) si un noeud requis manque, ou si le garde-fou echoue
      ('Assign to Yahtec --Success-->' != GOOD_TARGETS => le modele a change).
    - {'status': 'active'} si la garde est deja cablee (idempotent, meta inchange).
    - {'status': 'applied', 'reused', 'getattr_i', 'filter_i', 'good_is'} sinon.
    """
    nodes, conns = meta['nodes'], meta['connections']
    idx = {n['name']: i for i, n in enumerate(nodes)}

    for req in (ORIG, ASSIGN, *GOOD_TARGETS):
        if req not in idx:
            sys.exit(f'Node requis introuvable : {req!r}')
    orig_i, assign_i = idx[ORIG], idx[ASSIGN]
    good_is = [idx[n] for n in GOOD_TARGETS]

    # Garde-fou : la branche de reference (Assign to Yahtec --Success-->) doit
    # aller EXACTEMENT vers GOOD_TARGETS. Sinon le rule chain a change -> abort.
    ref_success = {c['toIndex'] for c in conns
                   if c['fromIndex'] == assign_i and c['type'] == 'Success'}
    if ref_success != set(good_is):
        got = sorted(nodes[i]['name'] for i in ref_success)
        sys.exit(f'ERREUR garde-fou : "{ASSIGN}" --Success--> {got} != {GOOD_TARGETS}. '
                 'Le rule chain a change ; revalider a la main.')

    getattr_existing, filter_existing = idx.get(GETATTR), idx.get(FILTER)
    guard_active = getattr_existing is not None and any(
        c['fromIndex'] == orig_i and c['toIndex'] == getattr_existing and c['type'] == 'Success'
        for c in conns)
    if guard_active:
        return {'status': 'active'}

    if getattr_existing is not None and filter_existing is not None:
        getattr_i, filter_i, reused = getattr_existing, filter_existing, True
    else:
        nodes.append(_getattr_node()); getattr_i = len(nodes) - 1
        nodes.append(_filter_node());  filter_i  = len(nodes) - 1
        reused = False

    new_conns = [c for c in conns
                 if not (c['fromIndex'] == orig_i and c['toIndex'] == assign_i and c['type'] == 'Success')]
    new_conns += [
        {'fromIndex': orig_i,    'toIndex': getattr_i, 'type': 'Success'},
        {'fromIndex': getattr_i, 'toIndex': filter_i,  'type': 'Success'},
        {'fromIndex': getattr_i, 'toIndex': filter_i,  'type': 'Failure'},
        {'fromIndex': filter_i,  'toIndex': assign_i,  'type': 'False'},
    ]
    new_conns += [{'fromIndex': filter_i, 'toIndex': ti, 'type': 'True'} for ti in good_is]
    meta['connections'] = new_conns
    return {'status': 'applied', 'reused': reused,
            'getattr_i': getattr_i, 'filter_i': filter_i, 'good_is': good_is}


def _show_true_branch(meta, label):
    nodes = meta['nodes']
    fi = next((i for i, n in enumerate(nodes) if n['name'] == FILTER), None)
    if fi is None:
        print(f'  [{label}] noeud {FILTER!r} absent'); return
    print(f'  [{label}] {FILTER} --True-->')
    for c in meta['connections']:
        if c['fromIndex'] == fi and c['type'] == 'True':
            print(f'      -> {nodes[c["toIndex"]]["name"]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    t = token_or_login(args.user, args.pwd)
    meta = http_get(f'/api/ruleChain/{RC_ID}/metadata', t)

    info = apply_guard(meta)  # peut sys.exit sur garde-fou
    if info['status'] == 'active':
        print('garde deja active -> idempotent skip')
        return

    print(f'nodes: {"reused" if info["reused"] else "+2"} '
          f'({GETATTR} @ {info["getattr_i"]}, {FILTER} @ {info["filter_i"]})')
    print(f'rewire: {ORIG} --Success--> {GETATTR} --> {FILTER} '
          f'--True--> {GOOD_TARGETS} / --False--> {ASSIGN}')
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

    meta2 = http_get(f'/api/ruleChain/{RC_ID}/metadata', t)
    print('Relecture de verification :')
    _show_true_branch(meta2, 'RELU')


if __name__ == '__main__':
    main()

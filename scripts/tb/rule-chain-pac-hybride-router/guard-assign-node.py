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

Convergent : skip (no-op) seulement si le cablage est deja exactement celui desire,
sinon (re)cable/repare la branche True meme si le garde etait deja present.
Reutilise les nodes orphelins. Dry-run par defaut ; --apply pour ecrire.
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

    Declaratif/convergent : force TOUJOURS le cablage getattr/filter vers le
    resultat desire (ORIG->getattr->filter, filter--False-->assign,
    filter--True-->GOOD_TARGETS), meme si les noeuds existent deja. Repare donc
    une branche True corrompue (ex: filter--True-->'save TS (per-id device)',
    le bug historique de fix-guard-true-branch.py) au lieu de la laisser en
    place sous pretexte que la garde est "presente".

    - sys.exit(...) si un noeud requis manque, ou si le garde-fou echoue
      ('Assign to Yahtec --Success-->' != GOOD_TARGETS => le modele a change).
    - {'status': 'active'} seulement si le cablage est DEJA exactement celui
      desire (vrai no-op, meta inchange).
    - {'status': 'applied', 'reused', 'getattr_i', 'filter_i', 'good_is'} sinon
      (insertion neuve OU reparation d'un cablage existant mais incorrect).
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

    # Reutilise les nodes getattr/filter s'ils sont deja tous les deux presents,
    # sinon les ajoute. Convergent : ne fait JAMAIS confiance a leur cablage actuel,
    # celui-ci est entierement re-derive plus bas (repare une branche True corrompue).
    getattr_existing, filter_existing = idx.get(GETATTR), idx.get(FILTER)
    if getattr_existing is not None and filter_existing is not None:
        getattr_i, filter_i, reused = getattr_existing, filter_existing, True
    else:
        nodes.append(_getattr_node()); getattr_i = len(nodes) - 1
        nodes.append(_filter_node());  filter_i  = len(nodes) - 1
        reused = False

    desired = [
        (orig_i, getattr_i, 'Success'),
        (getattr_i, filter_i, 'Success'),
        (getattr_i, filter_i, 'Failure'),
        (filter_i, assign_i, 'False'),
    ] + [(filter_i, ti, 'True') for ti in good_is]

    def _managed(c):
        # Edges que cette fonction possede et re-derive entierement : tout ce qui
        # part de getattr_i/filter_i, plus l'ancienne arete directe ORIG--Success-->ASSIGN.
        return (c['fromIndex'] in (getattr_i, filter_i)) or \
               (c['fromIndex'] == orig_i and c['type'] == 'Success' and c['toIndex'] in (assign_i, getattr_i))

    kept = [c for c in conns if not _managed(c)]
    new_conns = kept + [{'fromIndex': a, 'toIndex': b, 'type': t} for (a, b, t) in desired]

    def _edgeset(cs):
        return {(c['fromIndex'], c['toIndex'], c['type']) for c in cs}

    if reused and _edgeset(new_conns) == _edgeset(conns):
        return {'status': 'active'}

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

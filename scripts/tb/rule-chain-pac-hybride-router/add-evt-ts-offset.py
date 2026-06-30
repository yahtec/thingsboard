#!/usr/bin/env python3
"""
Fix collision evt : deux transitions de defaut dans la MEME seconde RTC se
stockaient au meme ts -> collision de PK ts_kv (entity_id, key, ts) sur les cles
PARTAGEES (evt_fault, evt_type, evt_status, evt_id, evt_device, evt_date,
evt_time) -> un seul defaut survit. Cas typique : reset firmware qui met tous
les bits de defaut a 0 simultanement (vu sur Serris 2623001001 le 19-06 :
R290 (111) ecrase par G20 (112), meme seconde 16:08:51).

Cause :
  - "save TS (per-id device)" a useServerTs=false -> utilise metadata.ts
  - metadata.ts = horloge RTC firmware a la SECONDE (ts % 1000 == 0)
  - les cles evt_* sont partagees entre tous les defauts d'un device

Fix chirurgical :
  Inserer un node TBEL(JS) "evt ts offset" sur l'arete
  [Filter HPs present v2] --False--> [save TS (per-id device)]
  qui decale metadata.ts d'un offset DETERMINISTE par (evt_fault, evt_device) :

      ts = floor(ts/1000)*1000 + ((evt_fault*8 + evt_device) % 1000)

  - meme evenement retransmis (cadence 1-2 s) -> meme offset -> IDEMPOTENT
    (se fusionne en une ligne, gain de lignes preserve)
  - defauts differents meme seconde -> offsets differents -> PLUS de collision
  - deux defauts sur le MEME device : fault*8 injectif -> jamais de collision
  - max offset (fault 114, dev 68) = 980 < 1000 -> reste dans la seconde

Aucun impact :
  - branche live (HPs present) intacte (autre node Save TS pac_v2)
  - widget events_history : appariement par fault|device, dedup 12 s inchanges
  - guard : n'agit que si msg.evt_fault est present (passe-plat sinon)

Idempotent : si le node "evt ts offset" existe deja, met juste a jour sa config
et verifie le cablage.

Usage:
  # validation HORS-LIGNE sur un backup (aucun reseau, aucun POST) :
  add-evt-ts-offset.py --from-file scripts/tb/rule-chain-pac-hybride-router/backup/metadata.before_nbpump.20260612-180514.json

  # dry-run sur la prod (GET + plan, pas de POST) :
  add-evt-ts-offset.py --pwd <pwd> --dry-run

  # application reelle :
  add-evt-ts-offset.py --pwd <pwd>
"""

import argparse, json, sys, time, os, copy, urllib.request, urllib.error

RC_ID        = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
FILTER_NODE  = 'Filter HPs present v2'
SAVE_TS_NODE = 'save TS (per-id device)'
NEW_NODE     = 'evt ts offset'
LINK_TYPE    = 'False'

JS_SCRIPT = (
    "var f = msg.evt_fault;\n"
    "if (f !== null && f !== undefined && metadata.ts) {\n"
    "    var base = Math.floor(Number(metadata.ts) / 1000) * 1000;\n"
    "    var dev = Number(msg.evt_device);\n"
    "    if (isNaN(dev)) { dev = 0; }\n"
    "    var off = ((Number(f) * 8 + dev) % 1000 + 1000) % 1000;\n"
    "    metadata.ts = \"\" + (base + off);\n"
    "}\n"
    "return {msg: msg, metadata: metadata, msgType: msgType};"
)


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


def new_node(layout_x, layout_y):
    return {
        "type": "org.thingsboard.rule.engine.transform.TbTransformMsgNode",
        "name": NEW_NODE,
        "debugSettings": None,
        "singletonMode": False,
        "queueName": None,
        "configurationVersion": 0,
        "configuration": {"scriptLang": "JS", "jsScript": JS_SCRIPT, "tbelScript": ""},
        "additionalInfo": {
            "description": ("Anti-collision ts_kv : decale metadata.ts de "
                            "(evt_fault*8 + evt_device) ms pour que deux defauts de la meme "
                            "seconde n'ecrasent pas leurs cles partagees. Idempotent par "
                            "retransmission."),
            "layoutX": layout_x, "layoutY": layout_y,
        },
    }


def apply_patch(meta):
    """Mutates meta in place. Returns a list of human-readable change lines."""
    nodes = meta['nodes']
    conns = meta['connections']
    changes = []

    def idx(name):
        return next((i for i, n in enumerate(nodes) if n.get('name') == name), None)

    filt_idx = idx(FILTER_NODE)
    save_idx = idx(SAVE_TS_NODE)
    if filt_idx is None: sys.exit(f'Node introuvable : {FILTER_NODE}')
    if save_idx is None: sys.exit(f'Node introuvable : {SAVE_TS_NODE}')

    nn_idx = idx(NEW_NODE)
    if nn_idx is None:
        # placer le node a cote du save node
        sx = nodes[save_idx].get('additionalInfo', {}).get('layoutX', 760)
        sy = nodes[save_idx].get('additionalInfo', {}).get('layoutY', 50)
        nodes.append(new_node(sx - 200, sy + 160))
        nn_idx = len(nodes) - 1
        changes.append(f'+ node "{NEW_NODE}" (index {nn_idx})')
    else:
        nodes[nn_idx]['configuration'] = {"scriptLang": "JS", "jsScript": JS_SCRIPT, "tbelScript": ""}
        changes.append(f'~ node "{NEW_NODE}" deja present (index {nn_idx}) : config mise a jour')

    def has(fr, to, ty):
        return any(c['fromIndex'] == fr and c['toIndex'] == to and c['type'] == ty for c in conns)

    # retirer l'arete directe Filter --False--> Save
    before = len(conns)
    meta['connections'] = [c for c in conns
                           if not (c['fromIndex'] == filt_idx and c['toIndex'] == save_idx and c['type'] == LINK_TYPE)]
    conns = meta['connections']
    if len(conns) < before:
        changes.append(f'- [{FILTER_NODE}] --{LINK_TYPE}--> [{SAVE_TS_NODE}] (arete directe retiree)')

    if not has(filt_idx, nn_idx, LINK_TYPE):
        conns.append({'fromIndex': filt_idx, 'toIndex': nn_idx, 'type': LINK_TYPE})
        changes.append(f'+ [{FILTER_NODE}] --{LINK_TYPE}--> [{NEW_NODE}]')
    if not has(nn_idx, save_idx, 'Success'):
        conns.append({'fromIndex': nn_idx, 'toIndex': save_idx, 'type': 'Success'})
        changes.append(f'+ [{NEW_NODE}] --Success--> [{SAVE_TS_NODE}]')

    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true', help='GET + plan, pas de POST')
    ap.add_argument('--from-file', help='valide hors-ligne sur un backup metadata local (pas de reseau)')
    args = ap.parse_args()

    if args.from_file:
        with open(args.from_file, 'rb') as f:
            meta = json.loads(f.read().decode('utf-8'))
        before = copy.deepcopy(meta)
        changes = apply_patch(meta)
        print('=== VALIDATION HORS-LIGNE ===')
        print(f'Nodes       : {len(before["nodes"])} -> {len(meta["nodes"])}')
        print(f'Connections : {len(before["connections"])} -> {len(meta["connections"])}')
        print('Changements :')
        for c in changes: print('  ' + c)
        print('\nScript JS du node :')
        print('  ' + JS_SCRIPT.replace('\n', '\n  '))
        # relire l'idempotence
        meta2 = copy.deepcopy(meta)
        ch2 = apply_patch(meta2)
        idem = (len(meta2['nodes']) == len(meta['nodes']) and
                len(meta2['connections']) == len(meta['connections']))
        print(f'\nIdempotence (2e passe) : nodes/connections stables = {idem} ; actions 2e passe = {ch2}')
        return

    if not args.pwd:
        sys.exit('--pwd requis (ou utilise --from-file pour la validation hors-ligne)')

    token = login(args.user, args.pwd)
    meta = http_get(f'/api/ruleChain/{RC_ID}/metadata', token)

    ts = time.strftime('%Y%m%d-%H%M%S')
    bdir = 'scripts/tb/rule-chain-pac-hybride-router/backup'
    os.makedirs(bdir, exist_ok=True)
    bpath = f'{bdir}/metadata.before_evt_ts_offset.{ts}.json'
    with open(bpath, 'wb') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup  : {bpath}')

    n0, c0 = len(meta['nodes']), len(meta['connections'])
    changes = apply_patch(meta)
    print(f'Nodes       : {n0} -> {len(meta["nodes"])}')
    print(f'Connections : {c0} -> {len(meta["connections"])}')
    print('Changements :')
    for c in changes: print('  ' + c)

    if args.dry_run:
        print('\nDRY-RUN : rien envoye.')
        return

    result = http_post('/api/ruleChain/metadata', meta, token)
    print(f'\nRule chain mise a jour. Nodes={len(result.get("nodes", []))} '
          f'Connections={len(result.get("connections", []))}')
    print(f'\nROLLBACK : add-evt-ts-offset.py --pwd <pwd> est idempotent, mais pour revenir '
          f'a l\'etat anterieur, re-POST le backup :\n  {bpath}')


if __name__ == '__main__': main()

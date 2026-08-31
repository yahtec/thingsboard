#!/usr/bin/env python3
"""
Garde-fou trim() sur le n de serie recu des automates.

Incident du 2026-08-28 : un automate a emis id = "2610000001\\r\\n" (retour-chariot
reste dans le champ de saisie). Chaine des consequences :

  1. node "extract id -> metadata" : metadata.targetDeviceName = String(msg.id)
     -> le retour-chariot passe tel quel
  2. node "originator -> device(${id})" cherche un DEVICE nomme "2610000001\\r\\n"
     -> introuvable -> Failure
  3. -> "wrap evt_unknown_id" -> bufferise sur le hub heatPumpHybride
  4. provision_watcher.py (cron 1/min, /home/dump/tb-dispatcher/) lit le buffer,
     ne strip pas non plus, et CREE un device fantome nomme "2610000001\\r\\n",
     l'assigne au customer yahtec et y rejoue le payload.

Resultat : 56 lignes de telemetrie aiguillees sur un 6e device parasite, et le
vrai device 2610000001 muet. L'alarme UnknownInstallation a bien ete levee mais
elle etait deja ouverte depuis le 2026-06-01, donc invisible (TbCreateAlarmNode
met a jour l'alarme active au lieu d'en creer une nouvelle).

Fix chirurgical (ce script) :
  node "extract id -> metadata" -> String(msg.id).trim()

Effet : "2610000001\\r\\n" resout vers le device "2610000001" existant. La donnee
arrive directement au bon endroit -- pas d'evt_unknown_id, pas d'alarme, pas de
passage par le watcher, pas de device fantome.

Seconde ligne de defense (hors de ce script, sur le serveur) :
  provision_watcher.py : inst_id = str(data.get("id")).strip()

Ce que le patch NE change PAS :
  - le cablage : aucune arete ajoutee ou retiree, aucun node cree
  - les autres nodes
  - le contrat de sortie du node : {msg, metadata, msgType}
  - un id deja propre : String("2610000001").trim() === "2610000001"

Cas limite assume : un id entierement blanc ("   ") devient "" -> le node 2 echoue
-> evt_unknown_id + alarme. Echec VISIBLE, et surtout pas de device fantome.
Le node "id present?" en amont ne filtre que l'absence et la chaine vide stricte.

Idempotent : re-executer ne fait rien si le trim est deja en place.

Usage:
  # validation HORS-LIGNE sur un backup (aucun reseau, aucun POST) :
  add-serial-trim.py --from-file scripts/tb/rule-chain-pac-hybride-router/backup/<f>.json

  # dry-run sur la prod (GET + plan, pas de POST) :
  add-serial-trim.py --pwd <pwd> --dry-run

  # application reelle :
  add-serial-trim.py --pwd <pwd>
"""

import argparse, json, sys, time, os, copy, urllib.request, urllib.error

RC_ID       = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL    = 'https://thingsboard.tsmart.fr'
TARGET_NODE = 'extract id -> metadata'

JS_SCRIPT = (
    "metadata.targetDeviceName = String(msg.id).trim();\n"
    "return {msg: msg, metadata: metadata, msgType: msgType};"
)

# TBEL (MVEL) : dormant tant que scriptLang vaut JS, mais on le patche pour qu'une
# bascule ulterieure du node en TBEL ne reintroduise pas le bug.
TBEL_SCRIPT = (
    "metadata.targetDeviceName = (msg.id + '').trim();\n"
    "return {msg: msg, metadata: metadata, msgType: msgType};"
)


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o:
        return json.loads(o.read().decode('utf-8'))


def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=120) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def token_or_login(user, pwd):
    """TB_TOKEN (env) > --pwd > TB_USER+TB_PASS (env). Le dernier cas evite de
    faire apparaitre un mot de passe dans une ligne de commande :
        source scripts/tb/gas/creds-from-server.sh"""
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if pwd:
        return login(user, pwd)
    env_user, env_pwd = os.environ.get('TB_USER'), os.environ.get('TB_PASS')
    if env_user and env_pwd:
        return login(env_user, env_pwd)
    sys.exit('Fournir TB_TOKEN (env), --pwd, ou TB_USER+TB_PASS (env) '
             '-- ou --from-file pour la validation hors-ligne')


def apply_patch(meta):
    """Mutate meta in place. Return a list of human-readable change lines.

    Empty list == deja applique (idempotent)."""
    node = next((n for n in meta['nodes'] if n.get('name') == TARGET_NODE), None)
    if node is None:
        sys.exit(f'Node introuvable : {TARGET_NODE}')

    cfg = node.setdefault('configuration', {})
    changes = []

    if cfg.get('jsScript') != JS_SCRIPT:
        cfg['jsScript'] = JS_SCRIPT
        changes.append(f'+ trim() pose sur le jsScript de "{TARGET_NODE}"')
    if cfg.get('tbelScript') != TBEL_SCRIPT:
        cfg['tbelScript'] = TBEL_SCRIPT
        changes.append(f'+ trim() pose sur le tbelScript de "{TARGET_NODE}"')

    return changes


def _report(meta, changes):
    node = next(n for n in meta['nodes'] if n['name'] == TARGET_NODE)
    if changes:
        for c in changes:
            print('  ' + c)
    else:
        print('  (rien a faire : le trim est deja en place)')
    print(f'\nscriptLang actif : {node["configuration"].get("scriptLang")}')
    print('jsScript :')
    print('  ' + node['configuration']['jsScript'].replace('\n', '\n  '))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true', help='GET + plan, pas de POST')
    ap.add_argument('--from-file', help='valide hors-ligne sur un backup local (pas de reseau)')
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
        _report(meta, changes)
        meta2 = copy.deepcopy(meta)
        ch2 = apply_patch(meta2)
        print(f'\nIdempotence (2e passe) : identique = {meta2 == meta} ; actions = {ch2}')
        return

    token = token_or_login(args.user, args.pwd)
    meta = http_get(f'/api/ruleChain/{RC_ID}/metadata', token)

    ts = time.strftime('%Y%m%d-%H%M%S')
    bdir = 'scripts/tb/rule-chain-pac-hybride-router/backup'
    os.makedirs(bdir, exist_ok=True)
    bpath = f'{bdir}/metadata.before_serial_trim.{ts}.json'
    with open(bpath, 'wb') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup  : {bpath}')

    n0, c0 = len(meta['nodes']), len(meta['connections'])
    changes = apply_patch(meta)
    print(f'Nodes       : {n0} -> {len(meta["nodes"])}   (doit rester identique)')
    print(f'Connections : {c0} -> {len(meta["connections"])}   (doit rester identique)')
    print('Changements :')
    _report(meta, changes)

    if args.dry_run:
        print('\nDRY-RUN : rien envoye.')
        return
    if not changes:
        print('\nRien a envoyer.')
        return

    result = http_post('/api/ruleChain/metadata', meta, token)
    print(f'\nRule chain mise a jour. Nodes={len(result.get("nodes", []))} '
          f'Connections={len(result.get("connections", []))}')
    print(f'\nROLLBACK : re-POST le backup\n  {bpath}')


if __name__ == '__main__':
    main()

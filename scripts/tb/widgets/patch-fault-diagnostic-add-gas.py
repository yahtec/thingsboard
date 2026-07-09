#!/usr/bin/env python3
"""
Patch widget fault_diagnostic : ajoute les 4 cles gaz du snapshot firmware 2026-07-08.
- gas_r290_conc / gas_g20_conc : concentration (%), tableau + courbe PAC
- gas_r290_err  / gas_g20_err  : registre de flags, tableau seul (0 -> OK)

Spec : docs/superpowers/specs/2026-07-09-snapshot-gaz-fault-diagnostic-design.md
Idempotent via marqueur __GAZ_SNAPSHOT_PATCH__. Patche le source LIVE (jamais le backup).

Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python patch-fault-diagnostic-add-gas.py [--dry-run]
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL = 'https://thingsboard.tsmart.fr'
FQN      = 'tduo.fault_diagnostic'
MARKER   = '__GAZ_SNAPSHOT_PATCH__'

# --- Remplacements (ancres verifiees uniques contre le live v77) -------------
R_KEYMETA = ('KEY_META',
  'var KEY_META = {',
  'var KEY_META = {\n'
  '    // ' + MARKER + ' : gaz / securite (snapshot firmware 2026-07-08), libelles ASCII\n'
  "    gas_r290_conc:{l:'Concentration R290',u:'%',s:1,d:1},\n"
  "    gas_g20_conc :{l:'Concentration G20', u:'%',s:1,d:1},\n"
  "    gas_r290_err :{l:'Defaut capteur R290 (registre)',u:'',s:1,d:0},\n"
  "    gas_g20_err  :{l:'Defaut capteur G20 (registre)', u:'',s:1,d:0},")

R_ENUM = ('ENUM_LABELS',
  'var ENUM_LABELS = {',
  'var ENUM_LABELS = {\n'
  "    gas_r290_err:{0:'OK'},\n"
  "    gas_g20_err :{0:'OK'},")

R_TABLE = ('SECTION_TABLES',
  "'c_fc0','c_fc1','c_fc2'\n        ]}\n    ],",
  "'c_fc0','c_fc1','c_fc2'\n"
  "        ]},\n"
  "        {title:'Gaz / Securite', keys:[\n"
  "            'gas_r290_conc','gas_g20_conc','gas_r290_err','gas_g20_err'\n"
  "        ]}\n"
  "    ],")

R_CHART = ('SNAP_PAC_CHART',
  "        {key:'c_iv',  label:'U. compr. in',    unit:'V',  d:0, color:'#795548', yMin:0,   yMax:400}",
  "        {key:'c_iv',  label:'U. compr. in',    unit:'V',  d:0, color:'#795548', yMin:0,   yMax:400},\n"
  "        {key:'gas_r290_conc', label:'Conc. R290', unit:'%', d:1, color:'#ff6f00', yMin:0, yMax:100},\n"
  "        {key:'gas_g20_conc',  label:'Conc. G20',  unit:'%', d:1, color:'#00acc1', yMin:0, yMax:100}")

REPLACEMENTS = [R_KEYMETA, R_ENUM, R_TABLE, R_CHART]
NEW_KEYS = ['gas_r290_conc', 'gas_g20_conc', 'gas_r290_err', 'gas_g20_err']

def apply_patch(cs):
    """Applique les 4 remplacements. Retourne (new_cs, notes). Leve si une ancre != 1 fois."""
    if MARKER in cs:
        return cs, ['deja patche (skip)']
    new = cs; notes = []
    for name, old, rep in REPLACEMENTS:
        n = new.count(old)
        if n != 1:
            raise SystemExit(f'  [{name}] ancre trouvee {n} fois (attendu 1) -- le source a change')
        new = new.replace(old, rep, 1)
        notes.append(f'[{name}] OK (+{len(rep)-len(old)} c)')
    for k in NEW_KEYS:
        if new.count(k) < 1:
            raise SystemExit(f'  validation: cle {k} absente apres patch')
    return new, notes

# --- REST helpers -----------------------------------------------------------
def _req(path, token, data=None, method='GET'):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
    h = {'X-Authorization': 'Bearer ' + token}
    if body is not None: h['Content-Type'] = 'application/json; charset=utf-8'
    r = urllib.request.Request(BASE_URL + path, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'{method} {path} -> HTTP {e.code}: {e.read().decode("utf-8","replace")[:500]}')

def _login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(BASE_URL + '/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']

def _resolve_id(token):
    infos = _req('/api/widgetTypes?pageSize=1000&page=0&tenantOnly=true', token)
    for w in infos.get('data', []):
        if w.get('fqn') == FQN:
            return w['id']['id']
    sys.exit('widget fqn introuvable: ' + FQN)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true', help='GET + patch en memoire, pas de POST')
    a = ap.parse_args()
    token = os.environ.get('TB_TOKEN')
    if not token:
        if not a.pwd: sys.exit('Fournir TB_TOKEN (env) ou --pwd')
        token = _login(a.user, a.pwd)

    wid = _resolve_id(token)
    w = _req('/api/widgetType/' + wid, token)
    print(f'Widget {w.get("name")} ({w.get("fqn")}) v{w.get("version")} id={wid}')
    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Deja patche (idempotent skip)'); return

    orig_serialized = json.dumps(w, ensure_ascii=False, indent=2)  # backup AVANT modif
    new, notes = apply_patch(cs)
    for n in notes: print('  ' + n)
    w['descriptor']['controllerScript'] = new
    json.dumps(w, ensure_ascii=False)  # round-trip JSON : leve si structure invalide

    if a.dry_run:
        print(f'DRY-RUN: controllerScript {len(cs)} -> {len(new)} c. Pas de POST.')
        return

    here = os.path.dirname(os.path.abspath(__file__))
    bdir = os.path.join(here, '..', 'backup', 'widgets-tduo-v1')
    os.makedirs(bdir, exist_ok=True)
    bpath = os.path.join(bdir, 'fault_diagnostic.before_gas.' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    open(bpath, 'w', encoding='utf-8').write(orig_serialized)
    print(f'  Backup original: {bpath}')
    resp = _req('/api/widgetType', token, data=w, method='POST')
    print(f'POST OK. Nouvelle version: {resp.get("version","?")}')

if __name__ == '__main__':
    main()

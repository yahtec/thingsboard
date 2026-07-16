#!/usr/bin/env python3
"""
Fix echelle des concentrations gaz sur le widget fault_diagnostic.

Les concentrations gaz sont exprimees en %LFL x10 (spec firmware). La v78 les
affichait en '%' avec s:1 (faux : brut 125 => "125 %"). Correction : u:'%LFL',
s:0.1 (=> "12.5 %LFL"). Les registres *_err (flags) ne changent pas.

Idempotent via detection de u:'%LFL' deja present. Patche le source LIVE.

Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python patch-fault-diagnostic-fix-gas-scale.py [--dry-run]
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL = 'https://thingsboard.tsmart.fr'
FQN      = 'tduo.fault_diagnostic'
DONE_MARK = "gas_r290_conc:{l:'Concentration R290',u:'%LFL'"

REPLACEMENTS = [
  ('KEY_META r290',
   "gas_r290_conc:{l:'Concentration R290',u:'%',s:1,d:1},",
   "gas_r290_conc:{l:'Concentration R290',u:'%LFL',s:0.1,d:1},"),
  ('KEY_META g20',
   "gas_g20_conc :{l:'Concentration G20', u:'%',s:1,d:1},",
   "gas_g20_conc :{l:'Concentration G20', u:'%LFL',s:0.1,d:1},"),
  ('CHART r290',
   "{key:'gas_r290_conc', label:'Conc. R290', unit:'%', d:1, color:'#ff6f00', yMin:0, yMax:100}",
   "{key:'gas_r290_conc', label:'Conc. R290', unit:'%LFL', d:1, color:'#ff6f00', yMin:0, yMax:100}"),
  ('CHART g20',
   "{key:'gas_g20_conc',  label:'Conc. G20',  unit:'%', d:1, color:'#00acc1', yMin:0, yMax:100}",
   "{key:'gas_g20_conc',  label:'Conc. G20',  unit:'%LFL', d:1, color:'#00acc1', yMin:0, yMax:100}"),
]

def apply_patch(cs):
    if DONE_MARK in cs:
        return cs, ['deja corrige (skip)']
    new = cs; notes = []
    for name, old, rep in REPLACEMENTS:
        n = new.count(old)
        if n != 1:
            raise SystemExit(f'  [{name}] ancre trouvee {n} fois (attendu 1) -- source a change')
        new = new.replace(old, rep, 1)
        notes.append(f'[{name}] OK')
    return new, notes

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
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    token = os.environ.get('TB_TOKEN')
    if not token:
        if not a.pwd: sys.exit('Fournir TB_TOKEN (env) ou --pwd')
        token = _login(a.user, a.pwd)
    wid = _resolve_id(token)
    w = _req('/api/widgetType/' + wid, token)
    print(f'Widget {w.get("name")} ({w.get("fqn")}) v{w.get("version")} id={wid}')
    cs = w['descriptor']['controllerScript']
    if DONE_MARK in cs:
        print('  Deja corrige (idempotent skip)'); return
    orig_serialized = json.dumps(w, ensure_ascii=False, indent=2)
    new, notes = apply_patch(cs)
    for n in notes: print('  ' + n)
    w['descriptor']['controllerScript'] = new
    json.dumps(w, ensure_ascii=False)
    if a.dry_run:
        print(f'DRY-RUN: {len(cs)} -> {len(new)} c. Pas de POST.'); return
    here = os.path.dirname(os.path.abspath(__file__))
    bdir = os.path.join(here, '..', 'backup', 'widgets-tduo-v1'); os.makedirs(bdir, exist_ok=True)
    bpath = os.path.join(bdir, 'fault_diagnostic.before_gasscale.' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    open(bpath, 'w', encoding='utf-8').write(orig_serialized)
    print(f'  Backup original: {bpath}')
    resp = _req('/api/widgetType', token, data=w, method='POST')
    print(f'POST OK. Nouvelle version: {resp.get("version","?")}')

if __name__ == '__main__':
    main()

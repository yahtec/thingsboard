#!/usr/bin/env python3
"""
Patch widget fault_diagnostic : affiche les 4 codes de defaut BRUTS du snapshot.
- pac_fault1 / pac_fault2 / pac_fault3 : codes defaut PAC (registres bruts)
- boiler_fault1                        : code defaut chaudiere (registre brut)

Deja presents dans KEY_META (donc deja fetches), mais jamais affiches.
Ajoute un sous-tableau "Codes defaut (bruts)" dans la section PAC (tableau seul,
valeurs brutes, pas de traduction FAULT_LABELS, pas de courbe).

Spec : suite directe de docs/superpowers/specs/2026-07-09-snapshot-gaz-fault-diagnostic-design.md
Idempotent via marqueur __FAULTCODES_SNAPSHOT_PATCH__. Patche le source LIVE.

Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python patch-fault-diagnostic-add-faultcodes.py [--dry-run]
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL = 'https://thingsboard.tsmart.fr'
FQN      = 'tduo.fault_diagnostic'
MARKER   = '__FAULTCODES_SNAPSHOT_PATCH__'

# --- Remplacement : nouveau sous-tableau apres le bloc "Gaz / Securite" ------
# (ancre = fin du sous-tableau Gaz dans SECTION_TABLES['PAC'], verifiee unique sur v78)
R_TABLE = ('SECTION_TABLES',
  "'gas_r290_conc','gas_g20_conc','gas_r290_err','gas_g20_err'\n        ]}\n    ],",
  "'gas_r290_conc','gas_g20_conc','gas_r290_err','gas_g20_err'\n"
  "        ]},\n"
  "        {title:'Codes defaut (bruts)', keys:[\n"
  "            'pac_fault1','pac_fault2','pac_fault3','boiler_fault1'\n"
  "        ]}\n"
  "    ],")

REPLACEMENTS = [R_TABLE]
SHOWN_KEYS = ['pac_fault1', 'pac_fault2', 'pac_fault3', 'boiler_fault1']

def apply_patch(cs):
    """Applique le remplacement. Retourne (new_cs, notes). Leve si ancre != 1 fois."""
    if MARKER in cs:
        return cs, ['deja patche (skip)']
    new = cs; notes = []
    for name, old, rep in REPLACEMENTS:
        n = new.count(old)
        if n != 1:
            raise SystemExit(f'  [{name}] ancre trouvee {n} fois (attendu 1) -- le source a change')
        new = new.replace(old, rep, 1)
        notes.append(f'[{name}] OK (+{len(rep)-len(old)} c)')
    # marqueur d'idempotence porte par le titre du sous-tableau + commentaire
    new = new.replace("{title:'Codes defaut (bruts)', keys:[",
                      "{title:'Codes defaut (bruts)', keys:[ /* " + MARKER + " */", 1)
    if "{title:'Codes defaut (bruts)'" not in new:
        raise SystemExit('  validation: sous-tableau Codes defaut absent apres patch')
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
    bpath = os.path.join(bdir, 'fault_diagnostic.before_faultcodes.' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    open(bpath, 'w', encoding='utf-8').write(orig_serialized)
    print(f'  Backup original: {bpath}')
    resp = _req('/api/widgetType', token, data=w, method='POST')
    print(f'POST OK. Nouvelle version: {resp.get("version","?")}')

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Patch widget Fault Diagnostic : remplace les sfx camelCase HP{N}_-prefixed par
les vrais noms snake_case sans prefixe (= ce que l'automate envoie dans les
debug arrays autour des defauts).

Mapping (sfx widget -> key DB) :
  pHi        -> p_hp
  pLo        -> p_bp
  tLP        -> t_bp
  tHPh       -> t_hph (T° HP chaud)
  tHPf       -> t_hpc (T° HP froid)
  tEvap      -> t_evap
  tCond      -> t_cond
  tOH        -> t_oh
  tOut       -> t_ib (T sortie PAC = T entree chaudiere)
  boil_tOut  -> t_ob
  boil_press -> wp_b
  boil_rpm   -> b_fan
  boil_qe    -> wf_b
  pump_dP    -> pb_dp

Et hpPfx() retourne '' (pas de prefixe car keys snake_case directes).

Idempotent via marker __FAULT_DIAG_KEYMAP_PATCH__.
"""

import argparse, json, sys, time, urllib.request, urllib.error

WIDGET_ID = '5e6e2180-478e-11f1-a9c9-47ea18512754'
BASE_URL  = 'https://thingsboard.tsmart.fr'
MARKER    = '__FAULT_DIAG_KEYMAP_PATCH__'

# Liste des replacements sfx
SFX_REPLACEMENTS = [
    ("sfx:'pHi',",        "sfx:'p_hp',"),
    ("sfx:'pLo',",        "sfx:'p_bp',"),
    ("sfx:'tLP',",        "sfx:'t_bp',"),
    ("sfx:'tHPh',",       "sfx:'t_hph',"),
    ("sfx:'tHPf',",       "sfx:'t_hpc',"),
    ("sfx:'tEvap',",      "sfx:'t_evap',"),
    ("sfx:'tCond',",      "sfx:'t_cond',"),
    ("sfx:'tOH',",        "sfx:'t_oh',"),
    ("sfx:'tOut',",       "sfx:'t_ib',"),
    ("sfx:'boil_tOut',",  "sfx:'t_ob',"),
    ("sfx:'boil_press',", "sfx:'wp_b',"),
    ("sfx:'boil_rpm',",   "sfx:'b_fan',"),
    ("sfx:'boil_qe',",    "sfx:'wf_b',"),
    ("sfx:'pump_dP',",    "sfx:'pb_dp',"),
]

# hpPfx : remplacer par function qui retourne ''
OLD_HPPFX = """function hpPfx(evtDevice){
    if (evtDevice >= 50 && evtDevice <= 59) return 'HP' + (evtDevice - 49) + '_';
    return 'HP1_';
}"""

NEW_HPPFX = """function hpPfx(evtDevice){
    // """ + MARKER + """ : les debug arrays autour des defauts utilisent des
    // keys snake_case sans prefixe HP{N}_. Le mapping HP{N}_ camelCase n'est
    // plus pertinent depuis migration v2.
    return '';
}"""


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o: return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o: return json.loads(o.read().decode('utf-8'))
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
    t = login(args.user, args.pwd)
    w = http_get(f'/api/widgetType/{WIDGET_ID}', t)
    print(f'Widget v{w.get("version")}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/backup/widgets-tduo-v1/fault_diagnostic.before_keymap.{ts}.json','wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Already patched (idempotent)')
        return
    # Sfx replacements
    replaced = 0
    for old, new in SFX_REPLACEMENTS:
        if old in cs:
            cs = cs.replace(old, new, 1)
            replaced += 1
            print(f'  {old:40s} -> {new}')
    if replaced == 0:
        sys.exit('No sfx pattern matched (widget code may have changed)')
    # hpPfx replacement
    if OLD_HPPFX in cs:
        cs = cs.replace(OLD_HPPFX, NEW_HPPFX, 1)
        print(f'  hpPfx() -> returns empty (no HP{{N}}_ prefix)')
    else:
        print(f'  WARN: hpPfx pattern not found, skipping')
    w['descriptor']['controllerScript'] = cs
    resp = http_post('/api/widgetType', w, t)
    print(f'\nPosted v{resp.get("version")}')


if __name__ == '__main__': main()

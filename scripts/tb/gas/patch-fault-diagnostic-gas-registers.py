#!/usr/bin/env python3
"""Declare les registres capteurs gaz dans le widget Diagnostic defaut :
nouvelles cles KEY_META, enumerations alarme/mode, formateurs f:'ver' et
f:'errbits' routes vers __gasLib, et injection de la lib.

Idempotent. Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python patch-fault-diagnostic-gas-registers.py [--dry-run]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'widgets'))

import _wt_patch as wt          # noqa: E402
import gas_patch_lib as lib     # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
FQN = 'tduo.fault_diagnostic'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    tok = wt.token_or_login(a.user, a.pwd)
    w = wt.get_widget_by_fqn('tenant.' + FQN, tok)   # le GET exige le prefixe
    cs = w['descriptor']['controllerScript']
    print(f'{FQN} v{w.get("version")} — {len(cs)} caracteres')
    if lib.DONE_MARK in cs:
        print('  deja patche (lib a rafraichir)')
    try:
        new_cs, notes = lib.patch_diag(cs)
    except lib.AnchorError as e:
        sys.exit(f'  {e}')
    lib.node_check(new_cs)
    for n in notes:
        print('  ' + n)
    if a.dry_run:
        print(f'  DRY-RUN: {len(cs)} -> {len(new_cs)} c. Pas de POST.')
        return
    wt.backup(w, 'fault_diagnostic.before_gas_registers')
    w['descriptor']['controllerScript'] = new_cs
    resp = wt.post_widget(w, tok)
    print(f'  POST OK, version {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

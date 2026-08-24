#!/usr/bin/env python3
"""Retire l'instance du widget timeline des registres gaz, restaure la hauteur
automatique de l'etat diagnostic, et supprime le widget_type devenu orphelin.

Motif : voir l'amendement du 2026-08-24 dans le plan. A 1 echantillon/minute
l'excursion de concentration est invisible ; seul le bit d'alarme est observable,
et une ligne calculee dans le widget Diagnostic defaut y repond mieux.

Idempotent. Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python retire-gas-registers-widget.py [--dry-run] [--keep-type]
"""
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'widgets'))
sys.path.insert(0, os.path.join(HERE, '..', 'dashboards'))

import _lib_tb as tb            # noqa: E402
import _wt_patch as wt          # noqa: E402
import gas_patch_lib as lib     # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--keep-type', action='store_true')
    a = ap.parse_args()

    tok = wt.token_or_login(a.user, a.pwd)
    dash = tb.get_dashboard(tok)
    dash_orig = copy.deepcopy(dash)          # sauvegarde de l'ORIGINAL
    conf = dash['configuration']
    wid = lib.GAS_REGISTERS_WIDGET_ID
    notes = []

    if wid in conf['widgets']:
        del conf['widgets'][wid]
        notes.append('instance retiree de la table des widgets')
    st = conf['states'].get(lib.DIAG_STATE)
    if st is None:
        sys.exit(f'etat {lib.DIAG_STATE} introuvable')
    layout = st['layouts']['main']
    if wid in layout['widgets']:
        del layout['widgets'][wid]
        notes.append('instance retiree du layout')
    grid = layout.setdefault('gridSettings', {})
    if grid.get('autoFillHeight') is not True:
        grid['autoFillHeight'] = True
        grid['mobileAutoFillHeight'] = True
        notes.append('hauteur automatique restauree')

    if not notes:
        print('  rien a retirer (deja fait)')
    else:
        for n in notes:
            print('  ' + n)
        print(f"  widgets restants dans l'etat : {len(layout['widgets'])}")
        if a.dry_run:
            prev = os.path.join(HERE, 'preview-retire-gas-registers.json')
            with open(prev, 'wb') as f:
                f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
            print(f'  [dry-run] preview: {prev}')
        else:
            tb.backup(dash_orig, 'retire_gas_registers')
            tb.post_dashboard(dash, tok)

    if a.keep_type:
        print('  widget_type conserve (--keep-type)')
        return
    try:
        w = wt.get_widget_by_fqn('tenant.' + lib.GAS_REGISTERS_FQN, tok)
    except SystemExit:
        print('  widget_type absent (deja supprime)')
        return
    tid = (w.get('id') or {}).get('id')
    if not tid:
        sys.exit('  id du widget_type introuvable, suppression annulee')
    if a.dry_run:
        print(f'  [dry-run] DELETE /api/widgetType/{tid}')
        return
    wt.backup(w, 'gas_registers.widget_type.before_delete')
    tb.http_delete(f'/api/widgetType/{tid}', tok)
    print(f'  widget_type {lib.GAS_REGISTERS_FQN} supprime')


if __name__ == '__main__':
    main()

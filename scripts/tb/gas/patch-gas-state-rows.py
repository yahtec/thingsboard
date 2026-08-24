#!/usr/bin/env python3
"""Remplace les blocs gaz ecrits a la main par un appel a __gasLib.rows() dans les
deux widgets de table de la page PAC, et injecte la lib + la classe CSS d'alarme.

Idempotent : la presence de la lib dans la source vaut skip.

Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python patch-gas-state-rows.py [--dry-run]
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

TARGETS = [
    ('tsmart.pac_detail_top_wip', 'HP'),
    ('tsmart.pac_boiler_info', 'boil'),
]

CSS_MARK = '.pd-kv .v.v-alarm'
CSS_RULE = '\n/* etat gaz en alarme (regle R2) */\n.pd-kv .v.v-alarm{color:#e53935;font-weight:600}\n'


def add_css(css):
    """Ajout en fin de feuille : pas d'ancre a maintenir, donc rien a casser."""
    if CSS_MARK in css:
        return css, 'css deja presente (skip)'
    return css + CSS_RULE, f'css ajoutee (+{len(CSS_RULE)}c)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    tok = wt.token_or_login(a.user, a.pwd)
    for fqn, target in TARGETS:
        print(f'== {fqn} ({target})')
        w = wt.get_widget_by_fqn('tenant.' + fqn, tok)   # le GET exige le prefixe
        cs = w['descriptor']['controllerScript']
        if lib.DONE_MARK in cs:
            print('  deja patche (lib a rafraichir)')
        try:
            new_cs, notes = lib.patch_table(cs, target)
        except lib.AnchorError as e:
            sys.exit(f'  {e}')
        new_css, css_note = add_css(w['descriptor'].get('templateCss', ''))
        for n in notes + [css_note]:
            print('  ' + n)
        if a.dry_run:
            print(f'  DRY-RUN: {len(cs)} -> {len(new_cs)} c. Pas de POST.')
            continue
        wt.backup(w, f'{target}.before_gas_rows')
        w['descriptor']['controllerScript'] = new_cs
        w['descriptor']['templateCss'] = new_css
        resp = wt.post_widget(w, tok)
        print(f'  POST OK, version {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Aligne a GAUCHE le CADRE du camembert (tenant.tsmart.pac_usage_wip) sur le cadre du
graphe au-dessus (meme colonne). Le donut RESTE centre a l'interieur de la carte.

Cause : .usage-pie-host { max-width: 480px; margin: 0 auto; } -> la carte est centree
dans sa cellule (bord gauche rentre). Fix : margin: 0 (cale a gauche) + max-width: none
(la carte remplit la cellule comme le chart au-dessus).
Idempotent (marqueur 'max-width: none; margin: 0;'). Patche templateCss.
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python patch-pac-usage-align-left.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wt_patch as wt

FQN = 'tenant.tsmart.pac_usage_wip'
MARK = 'max-width: none; margin: 0;'
OLD = 'max-width: 480px; margin: 0 auto;'
NEW = 'max-width: none; margin: 0;'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    tok = wt.token_or_login(a.user, a.pwd)
    w = wt.get_widget_by_fqn(FQN, tok)
    print(f'Widget {w.get("fqn")} v{w.get("version")}')
    css = w['descriptor'].get('templateCss', '') or ''
    if MARK in css:
        print('  deja patche (skip)')
        return
    new = wt.apply_replacements(css, [('host-align-left', OLD, NEW)])
    if a.dry_run:
        print(f'DRY-RUN css {len(css)}->{len(new)}c, pas de POST')
        return
    wt.backup(w, 'pac_usage_wip.before_frame_align')
    w['descriptor']['templateCss'] = new
    r = wt.post_widget(w, tok)
    print(f'POST OK v{r.get("version")}')


if __name__ == '__main__':
    main()

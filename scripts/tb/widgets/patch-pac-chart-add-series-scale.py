#!/usr/bin/env python3
"""Ajoute le support d'un facteur d'echelle par serie au widget tenant.tsmart.pac_chart.

Chaque serie de settings.series peut porter un champ optionnel `scale` (number).
Retro-compatible : les series sans `scale` sont tracees inchangees (brut).
Necessaire pour la courbe 'Gaz / Securite' (concentrations %LFL = brut x0.1).
Idempotent (marqueur 'se.scale'). Base sur le controllerScript LIVE.
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python patch-pac-chart-add-series-scale.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wt_patch as wt

FQN = 'tenant.tsmart.pac_chart'
MARK = 'se.scale'

OLD = "var v=getField(p,se.field,n); var f=parseFloat(v); if(v!=null&&!isNaN(f)&&isFinite(f)) pts.push([ts,f]);"
NEW = "var v=getField(p,se.field,n); var f=parseFloat(v); if(v!=null&&!isNaN(f)&&isFinite(f)) pts.push([ts,se.scale!=null?f*se.scale:f]);"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    tok = wt.token_or_login(a.user, a.pwd)
    w = wt.get_widget_by_fqn(FQN, tok)
    print(f'Widget {w.get("fqn")} v{w.get("version")}')
    cs = w['descriptor']['controllerScript']
    if MARK in cs:
        print('  deja patche (skip)')
        return
    new = wt.apply_replacements(cs, [('scale', OLD, NEW)])
    if a.dry_run:
        print(f'DRY-RUN {len(cs)}->{len(new)}c, pas de POST')
        return
    wt.backup(w, 'pac_chart.before_scale')
    w['descriptor']['controllerScript'] = new
    r = wt.post_widget(w, tok)
    print(f'POST OK v{r.get("version")}')


if __name__ == '__main__':
    main()

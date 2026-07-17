#!/usr/bin/env python3
"""Affiche les unites sur le widget tenant.tsmart.pac_chart.

Chaque serie de settings.series peut porter un champ optionnel `unit` (string).
- l'unite est portee dans le dataset,
- affichee dans le tooltip (valeur + unite) et la legende (label (unite)),
- si TOUTES les series du graphe partagent la meme unite -> labels d'axe Y (valeur + unite).
Retro-compatible : series sans `unit` -> comportement inchange (aucune unite, pas de label Y).
Idempotent (marqueur 'datasets[0].unit'). Base sur le controllerScript LIVE.
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python patch-pac-chart-add-units.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wt_patch as wt

FQN = 'tenant.tsmart.pac_chart'
MARK = 'datasets[0].unit'

REPL = [
    ('dataset-unit',
     """return {label:se.label,color:se.color,pts:pts};""",
     """return {label:se.label,color:se.color,unit:se.unit,pts:pts};"""),
    ('U-def',
     """var svg='<svg width="'+W+'" height="'+Hh+'" viewBox="0 0 '+W+' '+Hh+'">';""",
     """var U=(datasets.length&&datasets.every(function(x){return (x.unit||'')===(datasets[0].unit||'');}))?(datasets[0].unit||''):''; var svg='<svg width="'+W+'" height="'+Hh+'" viewBox="0 0 '+W+' '+Hh+'">';"""),
    ('yaxis-label',
     """svg+='<line x1="'+mL+'" y1="'+y.toFixed(1)+'" x2="'+(W-mR)+'" y2="'+y.toFixed(1)+'" stroke="#eee"/>';""",
     """svg+='<line x1="'+mL+'" y1="'+y.toFixed(1)+'" x2="'+(W-mR)+'" y2="'+y.toFixed(1)+'" stroke="#eee"/>'; if(U) svg+='<text x="'+(mL-3)+'" y="'+(y-2).toFixed(1)+'" font-size="9" fill="#999" text-anchor="end">'+(Math.round(vv*10)/10)+' '+U+'</text>';"""),
    ('tooltip-unit',
     """></i>'+d.label+' : <b>'+(Math.round(best[1]*10)/10)+'</b></div>'""",
     """></i>'+d.label+' : <b>'+(Math.round(best[1]*10)/10)+(d.unit?' '+d.unit:'')+'</b></div>'"""),
    ('legend-unit',
     """></i>'+d.label+'</span>'""",
     """></i>'+d.label+(d.unit?' ('+d.unit+')':'')+'</span>'"""),
]


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
    new = wt.apply_replacements(cs, REPL)
    if a.dry_run:
        print(f'DRY-RUN {len(cs)}->{len(new)}c, pas de POST')
        return
    wt.backup(w, 'pac_chart.before_units')
    w['descriptor']['controllerScript'] = new
    r = wt.post_widget(w, tok)
    print(f'POST OK v{r.get("version")}')


if __name__ == '__main__':
    main()

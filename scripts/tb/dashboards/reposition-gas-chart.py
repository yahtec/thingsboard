#!/usr/bin/env python3
"""Ajuste l'instance courbe 'Gaz / Securite' du dashboard 'Mes Installations' (0964da30) :
  - ajoute unit='%LFL' aux 2 series (affichage unites, cf patch-pac-chart-add-units),
  - repositionne : courbe gaz a GAUCHE du camembert (usage), taille des autres graphes
    (sizeX=12, sizeY=5) ; le camembert passe a droite (col=12, sizeX=12, sizeY inchangee).
Idempotent (re-applique les memes valeurs).
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python reposition-gas-chart.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

STATE = 'donnees_HP1'
NID = 'a1b2c3d4-0730-4000-a000-000000000701'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    t = tb.token_or_login(a.user, a.pwd)
    dash = tb.get_dashboard(t)
    conf = dash['configuration']
    widgets = conf['widgets']
    lay = conf['states'][STATE]['layouts']['main']['widgets']

    if NID not in widgets or NID not in lay:
        sys.exit(f'Instance gaz {NID} absente du dashboard/layout -- lancer add-gas-chart-instance.py d abord')

    # 1. unites sur les series
    series = widgets[NID]['config']['settings'].get('series', [])
    for s in series:
        s['unit'] = '%LFL'
    print(f'  series avec unit=%LFL : {len(series)}')

    # 2. camembert (usage) a droite, demi-largeur
    donut_id = next((wid for wid in lay
                     if widgets.get(wid, {}).get('typeFullFqn') == 'tenant.tsmart.pac_usage_wip'), None)
    if not donut_id:
        sys.exit('Camembert (pac_usage_wip) introuvable dans le layout')
    drow = lay[donut_id].get('row', 26)
    lay[donut_id]['col'] = 12
    lay[donut_id]['sizeX'] = 12
    # sizeY / row du camembert inchanges

    # 3. courbe gaz a gauche, meme taille que les autres graphes
    lay[NID]['col'] = 0
    lay[NID]['row'] = drow
    lay[NID]['sizeX'] = 12
    lay[NID]['sizeY'] = 5
    print(f'  gaz -> col0 row{drow} 12x5 ; camembert {donut_id} -> col12 row{drow} 12x{lay[donut_id].get("sizeY")}')

    if a.dry_run:
        print('DRY-RUN : pas de POST.')
        return
    tb.backup(dash, 'reposition_gas_chart')
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Corrige la mise en page de l'etat donnees_HP1 ('Mes Installations' 0964da30) apres l'ajout gaz :
  - agrandit les cartes info devenues trop courtes :
      pac_detail_top_wip sizeY 6->8 (lignes R290) ; pac_boiler_info sizeY 4->6 (lignes G20 visibles),
  - camembert (usage) a GAUCHE (col0), courbe gaz a DROITE (col12), tous deux demi-largeur (12),
  - re-empile verticalement toutes les bandes (aucun chevauchement) selon leur ordre courant.
Idempotent (recalcule le meme layout a chaque run).
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python fix-pac-page-layout.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

STATE = 'donnees_HP1'
GAS = 'a1b2c3d4-0730-4000-a000-000000000701'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    t = tb.token_or_login(a.user, a.pwd)
    dash = tb.get_dashboard(t)
    conf = dash['configuration']
    w = conf['widgets']
    main = conf['states'][STATE]['layouts']['main']
    main.setdefault('gridSettings', {})['margin'] = 6   # espace inter-widgets reduit (12->6)
    lay = main['widgets']

    def fqn(wid):
        return w.get(wid, {}).get('typeFullFqn')

    # 1. hauteurs des cartes info
    for wid in lay:
        if fqn(wid) == 'tenant.tsmart.pac_detail_top_wip':
            lay[wid]['sizeY'] = 7   # 8 laissait du gris entre la table PAC et la barre retroview
        elif fqn(wid) == 'tenant.tsmart.pac_boiler_info':
            lay[wid]['sizeY'] = 6

    # 2. courbe gaz a GAUCHE (col0) / camembert a DROITE (col12), demi-largeur
    donut = next((wid for wid in lay if fqn(wid) == 'tenant.tsmart.pac_usage_wip'), None)
    if not donut:
        sys.exit('camembert (pac_usage_wip) introuvable')
    lay[donut]['col'] = 12
    lay[donut]['sizeX'] = 5    # largeur reduite (demande JE) ; col12 garde l'alignement gauche
    lay[donut]['sizeY'] = 7   # revert taille camembert (demande JE)
    if GAS in lay:
        lay[GAS]['col'] = 0
        lay[GAS]['sizeX'] = 12
        lay[GAS]['sizeY'] = 5

    # 3. reflow : regroupe par row courant, re-empile sequentiellement
    bands = {}
    for wid, l in lay.items():
        bands.setdefault(l.get('row', 0), []).append(wid)
    cur = 0
    for row in sorted(bands):
        ids = bands[row]
        h = max(lay[wid].get('sizeY', 1) for wid in ids)
        for wid in ids:
            lay[wid]['row'] = cur
        cur += h

    print(f'  reflow: {len(lay)} widgets, hauteur totale {cur}')
    for wid in sorted(lay, key=lambda k: (lay[k]['row'], lay[k].get('col', 0))):
        l = lay[wid]
        print(f"    {fqn(wid)} c{l['col']} r{l['row']} {l['sizeX']}x{l['sizeY']}")

    if a.dry_run:
        print('DRY-RUN : pas de POST.')
        return
    tb.backup(dash, 'fix_layout_gas')
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Ajoute une instance pac_chart 'Gaz / Securite' a l'etat donnees_HP1 du dashboard
final 'Mes Installations' (0964da30). Series conR290/conG20 avec scale 0.1 (%LFL),
resolues par le widget pac_chart via se.field -> HPs[n-1].<path> (cf patch scale).

Clone une instance pac_chart existante (preserve le binding datasource pac_v2),
lui donne un id fixe + les series gaz, et la place sous les courbes existantes.
Idempotent : skip si une instance settings.title == 'Gaz / Sécurité' existe deja.
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python add-gas-chart-instance.py [--dry-run]
"""
import argparse, copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

STATE = 'donnees_HP1'
NEWID = 'a1b2c3d4-0730-4000-a000-000000000701'
TITLE = 'Gaz / Sécurité'
GAS_SETTINGS = {
    'title': TITLE,
    'series': [
        {'label': 'Conc. R290', 'field': 'HP.conR290', 'color': '#ff6f00', 'scale': 0.1},
        {'label': 'Conc. G20', 'field': 'boil.conG20', 'color': '#00acc1', 'scale': 0.1},
    ],
}


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

    # Idempotence : deja present ?
    for wid, w in widgets.items():
        st = (w.get('config', {}) or {}).get('settings', {}) or {}
        if st.get('title') == TITLE:
            print(f'  instance "{TITLE}" deja presente (id={wid}) -- skip')
            return

    # Template : une instance pac_chart existante
    tpl_id = next((wid for wid, w in widgets.items()
                   if w.get('typeFullFqn') == 'tenant.tsmart.pac_chart'), None)
    if not tpl_id:
        sys.exit('Aucune instance pac_chart a cloner -- etat inattendu')
    nw = copy.deepcopy(widgets[tpl_id])
    nw['id'] = NEWID
    nw['config']['title'] = TITLE
    nw['config']['settings'] = copy.deepcopy(GAS_SETTINGS)

    # Layout donnees_HP1 : placer sous l'existant, pleine largeur
    lay = conf['states'][STATE]['layouts']['main']['widgets']
    chart_ids = [wid for wid in lay
                 if widgets.get(wid, {}).get('typeFullFqn') == 'tenant.tsmart.pac_chart']
    tpl_lay = copy.deepcopy(lay[chart_ids[0]]) if chart_ids else {'sizeY': 8}
    bottom = max((l.get('row', 0) + l.get('sizeY', 0)) for l in lay.values())
    tpl_lay['col'] = 0
    tpl_lay['row'] = bottom
    tpl_lay['sizeX'] = 24

    if NEWID in widgets:
        sys.exit(f'  id {NEWID} deja present dans widgets mais sans le titre attendu -- verifier manuellement')

    widgets[NEWID] = nw
    lay[NEWID] = tpl_lay
    print(f'  clone de {tpl_id} -> {NEWID} ; layout row={bottom} sizeY={tpl_lay.get("sizeY")} sizeX=24')

    if a.dry_run:
        print(f'DRY-RUN : widgets {len(widgets)}, {STATE} layout {len(lay)}. Pas de POST.')
        return
    tb.backup(dash, 'before_gas_chart')
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Ajoute les series de seuil au graphe Gaz / Securite, dans la config de
l'INSTANCE — le type tsmart.pac_chart sert 7 graphes et n'est pas touche.

Idempotent. Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python add-gas-threshold-series.py [--dry-run]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'dashboards'))

import _lib_tb as tb            # noqa: E402
import gas_patch_lib as lib     # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    t = tb.token_or_login(a.user, a.pwd)
    dash = tb.get_dashboard(t)
    widgets = dash['configuration']['widgets']
    wid = lib.GAS_CHART_WIDGET_ID
    if wid not in widgets:
        sys.exit(f'instance du graphe gaz introuvable: {wid}')
    cfg = widgets[wid]['config']
    avant = cfg.get('settings') or {}
    titre = avant.get('title', '?')
    print(f'instance {wid} — titre "{titre}"')
    new_settings, note = lib.add_threshold_series(avant)
    print('  ' + note)
    if new_settings == avant:
        return
    cfg['settings'] = new_settings
    if a.dry_run:
        prev = os.path.join(HERE, 'preview-gas-threshold.json')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'  [dry-run] preview: {prev}')
        return
    tb.backup(dash, 'gas_threshold_series')
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

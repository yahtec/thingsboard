#!/usr/bin/env python3
"""Pose une ligne de rappel (nom installation + n serie) en haut des 6 etats de
detail de 'Mes Installations' (0964da30) et retire le titre de la carte photo
(etat default). Idempotent.
Spec: docs/superpowers/specs/2026-07-21-dashboard-ligne-rappel-installation-design.md

Usage: set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
       python add-install-header-line.py --dry-run [--preview-file preview.json]
       python add-install-header-line.py          # applique (backup + POST)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb
import dash_header_lib as hdr


def _summary(cfg):
    for sid in hdr.HEADER_STATES:
        lay = hdr._state_main_widgets(cfg, sid)
        if lay is None:
            print(f'  {sid}: (absent)')
            continue
        rows = sorted((w.get('row', 0), wid[:8]) for wid, w in lay.items())
        print(f'  {sid}: ' + ', '.join(f'r{r}:{i}' for r, i in rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--preview-file')
    a = ap.parse_args()

    t = tb.token_or_login(a.user, a.pwd)
    dash = tb.get_dashboard(t)
    print(f"version live: {dash.get('version')}")
    dash['configuration'] = hdr.apply_all(hdr.get_config(dash))
    _summary(dash['configuration'])

    if a.preview_file:
        tb.export_json(dash, a.preview_file)
        print(f'preview -> {a.preview_file}')
    if a.dry_run:
        print('DRY-RUN : pas de POST.')
        return
    tb.backup(dash, 'install_header_line')
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

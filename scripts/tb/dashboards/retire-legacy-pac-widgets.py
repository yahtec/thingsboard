#!/usr/bin/env python3
"""Phase 5 : retire les 10 widgets legacy de donnees_HP1, ne garde que le widget
unifie, et le repositionne en plein ecran. Idempotent. Usage: --pwd <pwd> [--dry-run]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WID_UNIFIED = 'a1b2c3d4-0700-4000-a000-000000000001'
LEGACY_WIDS = [
    '49e69aac-15bc-32c4-c32d-c474cfeffa82',  # PAC Info
    'a1b2c3d4-0400-4000-a000-000000000001',  # Timeline
    'a1b2c3d4-0601-4000-a000-000000000001',  # PAC Chart Pressions
    'a1b2c3d4-0001-4000-a000-000000000001',  # PAC Chart Temperatures
    'a1b2c3d4-0602-4000-a000-000000000002',  # PAC Chart Frigo
    'a1b2c3d4-0603-4000-a000-000000000003',  # PAC Chart Compresseur
    'a1b2c3d4-0002-4000-a000-000000000002',  # Chaudiere Info
    'a1b2c3d4-0003-4000-a000-000000000003',  # Chaudiere Chart Temperatures
    'a1b2c3d4-0604-4000-a000-000000000004',  # Chaudiere Chart Bruleur
    'a1b2c3d4-9997-4000-a000-000000000097',  # Usage pie
]
FINAL_LAYOUT = {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 40, 'mobileOrder': 0, 'mobileHeight': 44}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'retire_legacy')
    conf = dash['configuration']
    lay = conf['states']['donnees_HP1']['layouts']['main']['widgets']

    if WID_UNIFIED not in lay:
        sys.exit('Widget unifie absent — lancer les phases 1-4 avant le nettoyage.')

    removed = []
    for wid in LEGACY_WIDS:
        if wid in conf['widgets']:
            del conf['widgets'][wid]
            removed.append(wid)
        lay.pop(wid, None)
    lay[WID_UNIFIED] = dict(FINAL_LAYOUT)
    print(f'  retires: {len(removed)} widgets ; unifie repositionne plein ecran {FINAL_LAYOUT}')
    print(f'  widgets restants dans l\'etat: {list(lay.keys())}')

    if args.dry_run:
        here = os.path.dirname(os.path.abspath(__file__))
        prev = os.path.join(here, 'preview-retire-legacy.json')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

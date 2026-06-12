#!/usr/bin/env python3
"""Phase 2 : retire les 4 widgets legacy de depart_chauffage, ne garde que le
widget chauffage unifie, repositionne plein ecran. Idempotent. Usage: --pwd <pwd> [--dry-run]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STATE = 'depart_chauffage'
WID_HEAT = 'a1b2c3d4-0710-4000-a000-000000000001'
LEGACY = [
    'a1b2c3d4-0502-4000-a000-000000000001',  # Chauffage Header
    'a1b2c3d4-0500-4000-a000-000000000001',  # Chauffage Info (calo)
    'a1b2c3d4-0400-4000-a000-000000000002',  # Timeline
    'a1b2c3d4-0501-4000-a000-000000000001',  # Chauffage Chart
]
FINAL_LAYOUT = {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 24, 'mobileOrder': 0, 'mobileHeight': 28}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'retire_legacy_heat')
    conf = dash['configuration']
    lay = conf['states'][STATE]['layouts']['main']['widgets']

    if WID_HEAT not in lay:
        sys.exit('Widget chauffage unifie absent — lancer la phase 1 avant le nettoyage.')

    removed = []
    for wid in LEGACY:
        if wid in conf['widgets']:
            del conf['widgets'][wid]
            removed.append(wid)
        lay.pop(wid, None)
    lay[WID_HEAT] = dict(FINAL_LAYOUT)
    print(f'  retires: {len(removed)} widgets ; unifie repositionne {FINAL_LAYOUT}')
    print(f'  widgets restants dans l\'etat: {list(lay.keys())}')

    if args.dry_run:
        here = os.path.dirname(os.path.abspath(__file__))
        prev = os.path.join(here, 'preview-retire-legacy-heat.json')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

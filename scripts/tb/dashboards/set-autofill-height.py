#!/usr/bin/env python3
"""Active autoFillHeight + mobileAutoFillHeight sur les gridSettings des etats
donnees_HP1 et depart_chauffage : le contenu remplit le viewport, supprime le
scroll de page parasite (vide sous le contenu sur PC) et le double-scroll mobile.
Idempotent. Usage: --pwd <pwd> [--dry-run]"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STATES = ['donnees_HP1', 'depart_chauffage']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'autofill')
    conf = dash['configuration']

    changed = False
    for sid in STATES:
        gs = conf['states'][sid]['layouts']['main'].setdefault('gridSettings', {})
        before = (gs.get('autoFillHeight'), gs.get('mobileAutoFillHeight'))
        gs['autoFillHeight'] = True
        gs['mobileAutoFillHeight'] = True
        after = (gs['autoFillHeight'], gs['mobileAutoFillHeight'])
        if before != after:
            changed = True
        print(f'  {sid}: autoFillHeight {before} -> {after}')

    if not changed:
        print('Deja applique. Rien a faire.')
        return

    if args.dry_run:
        print('[dry-run] pas de POST.')
        return
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()

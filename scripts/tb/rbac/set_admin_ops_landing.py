#!/usr/bin/env python3
"""Pose le dashboard d'atterrissage sur les comptes ADMIN_OPS.

Probleme : un ADMIN_OPS (chrome TSmart custom, pas de menu TB) qui se connecte
sans defaultDashboardId atterrit hors dashboard -> la barre yahtec-nav (gatee sur
URL dashboard) ne s'affiche pas. Fix : repliquer la config de td@ (PARTY qui
marche) = home+default dashboard "Mes Installations" en plein ecran, toolbar TB
masquee. Le chrome custom injecte la barre yahtec-nav par-dessus.

Merge non destructif : ne touche QUE les 4 champs dashboard, preserve
portfolioRole + le reste. Garde-fou : n'agit que si portfolioRole==ADMIN_OPS.
Dry-run par defaut. --apply pour ecrire. Token via TB_TOKEN.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import _lib_rbac as tb  # noqa: E402

DASH = '0964da30-3e56-11f1-bbfe-e1395562cba0'  # Mes Installations
TARGETS = ['je+user@yahtec.com', 'af+user@yahtec.com', 'ac@yahtec.com']
FIELDS = {
    'homeDashboardId': DASH,
    'homeDashboardHideToolbar': True,
    'defaultDashboardId': DASH,
    # IMPORTANT : fullscreen=FALSE. auth.service userForceFullscreen route
    # fullscreen=true -> /dashboard/{id} (SINGULIER, standalone, PAS de yahtec-nav) ;
    # false -> /dashboards/{id} (PLURIEL, dans home.component AVEC le yahtec-nav).
    # ADMIN_OPS + PARTY ont besoin du yahtec-nav -> DONC false.
    'defaultDashboardFullscreen': False,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='ecrit (defaut = dry-run)')
    ap.add_argument('--user', default=os.environ.get('TB_USER', 'je@yahtec.com'))
    ap.add_argument('--pwd', default=os.environ.get('TB_PWD'))
    args = ap.parse_args()
    t = tb.token_or_login(args.user, args.pwd)

    for email in TARGETS:
        u = tb.find_user_by_email(t, email)
        if not u:
            print(f'  ABSENT           : {email}')
            continue
        ai = dict(u.get('additionalInfo') or {})
        if ai.get('portfolioRole') != 'ADMIN_OPS':
            print(f'  SKIP (pas ADMIN_OPS, role={ai.get("portfolioRole")!r}) : {email}')
            continue
        changed = [k for k, v in FIELDS.items() if ai.get(k) != v]
        print(f'  {email} : champs a poser = {changed or "aucun (deja bon)"}')
        print(f'     AVANT: {json.dumps(ai, ensure_ascii=False, sort_keys=True)}')
        ai.update(FIELDS)
        print(f'     APRES: {json.dumps(ai, ensure_ascii=False, sort_keys=True)}')
        if args.apply and changed:
            u['additionalInfo'] = ai
            tb.http_post('/api/user', u, t)
            print('     -> ECRIT')

    if not args.apply:
        print('\nDRY-RUN : rien ecrit. Relancer avec --apply.')


if __name__ == '__main__':
    main()

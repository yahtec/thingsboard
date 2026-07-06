#!/usr/bin/env python3
"""Pose le landing yahtec (dashboard Mes Installations + yahtec-nav) sur TOUS les
non-devs (ADMIN_OPS + CUSTOMER_USER PARTY), en sautant les vrais tenant-admins dev.

Spec des 3 bandeaux (cahier des charges d'origine) :
- je@ / af@ (TENANT_ADMIN, pas de portfolioRole) -> barre TB NATIVE -> ON NE TOUCHE PAS.
- ADMIN_OPS (TENANT_ADMIN + portfolioRole=ADMIN_OPS) -> barre yahtec COMPLETE (Comptes/Param).
- PARTY (CUSTOMER_USER) -> barre yahtec SANS boutons admin.

Point cle (auth.service userForceFullscreen) : defaultDashboardFullscreen=true route
vers /dashboard/{id} (SINGULIER = fullscreen standalone, PAS de yahtec-nav) ; false
route vers /dashboards/{id} (PLURIEL = home.component AVEC yahtec-nav). Les non-devs
ont besoin du yahtec-nav -> fullscreen=FALSE.

Merge non destructif (4 champs seulement). Dry-run par defaut ; --apply pour ecrire.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import _lib_rbac as tb  # noqa: E402

DASH = '0964da30-3e56-11f1-bbfe-e1395562cba0'  # Mes Installations
FIELDS = {
    'homeDashboardId': DASH,
    'homeDashboardHideToolbar': True,
    'defaultDashboardId': DASH,
    'defaultDashboardFullscreen': False,  # cle : false => /dashboards/ => yahtec-nav
}


def is_dev(u):
    """Vrai tenant-admin dev (barre TB native) : on ne touche pas."""
    a = u.get('authority')
    ai = u.get('additionalInfo') or {}
    return a in ('TENANT_ADMIN', 'SYS_ADMIN') and ai.get('portfolioRole') != 'ADMIN_OPS'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='ecrit (defaut = dry-run)')
    ap.add_argument('--user', default=os.environ.get('TB_USER', 'je@yahtec.com'))
    ap.add_argument('--pwd', default=os.environ.get('TB_PWD'))
    args = ap.parse_args()
    t = tb.token_or_login(args.user, args.pwd)

    page = tb.http_get('/api/users?pageSize=1000&page=0', t)
    users = (page or {}).get('data', [])
    print(f'{len(users)} users au total.\n')

    for u in sorted(users, key=lambda x: x.get('email', '')):
        email = u.get('email')
        ai = dict(u.get('additionalInfo') or {})
        if is_dev(u):
            print(f'  SKIP dev natif    : {email} (authority={u.get("authority")}, role={ai.get("portfolioRole")})')
            continue
        role = ai.get('portfolioRole') or ('CUSTOMER_USER' if u.get('authority') == 'CUSTOMER_USER' else '?')
        changed = [k for k, v in FIELDS.items() if ai.get(k) != v]
        if not changed:
            print(f'  OK deja bon       : {email} ({role})')
            continue
        print(f'  {email} ({role}) : a changer = {changed}')
        print(f'     fullscreen: {ai.get("defaultDashboardFullscreen")!r} -> False ; defDash: {"oui" if ai.get("defaultDashboardId") else "NON -> pose"}')
        ai.update(FIELDS)
        if args.apply:
            u['additionalInfo'] = ai
            tb.http_post('/api/user', u, t)
            print('     -> ECRIT')

    if not args.apply:
        print('\nDRY-RUN : rien ecrit. Relancer avec --apply.')


if __name__ == '__main__':
    main()

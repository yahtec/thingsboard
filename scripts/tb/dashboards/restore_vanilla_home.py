#!/usr/bin/env python3
"""Restaure le home vanilla : retire le home dashboard AU NIVEAU TENANT.

Apres execution, GET /api/dashboard/home ne renvoie plus rien pour les
tenant-admin sans home dashboard perso -> le front charge le dashboard CE
par defaut (tenant_admin_home_page.json).

Methode = REST (POST /api/tenant/dashboard/home/info {dashboardId:null}) qui
passe par tenantService.saveTenant() et invalide le cache caffeine ; une
edition SQL brute ne purgerait PAS le cache (local JVM) sans restart.

Usage :
  TB_TOKEN=<jwt_tenant_admin> python restore_vanilla_home.py            # dry-run (affiche l'etat)
  TB_TOKEN=<jwt_tenant_admin> python restore_vanilla_home.py --apply    # applique
  python restore_vanilla_home.py --user je@yahtec.com --pwd '***' --apply
"""
import argparse, sys, json, urllib.request, urllib.error
from _lib_tb import BASE_URL, token_or_login, http_get


def post_empty_ok(path, body, t):
    """POST tolerant a une reponse 200 a corps vide (cas /tenant/dashboard/home/info)."""
    data = json.dumps(body).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{path}', data=data, method='POST',
        headers={'Content-Type': 'application/json', 'X-Authorization': f'Bearer {t}'})
    try:
        with urllib.request.urlopen(r, timeout=120) as o:
            return o.status
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {path} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true', help='applique le retrait (sinon dry-run)')
    args = ap.parse_args()

    t = token_or_login(args.user, args.pwd)

    print(f'BASE_URL: {BASE_URL}')
    before = http_get('/api/tenant/dashboard/home/info', t)
    print(f'AVANT  /tenant/dashboard/home/info -> {before}')

    if not args.apply:
        print('\n[dry-run] rien envoye. Relancer avec --apply pour retirer le home dashboard tenant.')
        return

    status = post_empty_ok('/api/tenant/dashboard/home/info', {'dashboardId': None}, t)
    print(f'POST   /tenant/dashboard/home/info -> HTTP {status}')
    after = http_get('/api/tenant/dashboard/home/info', t)
    print(f'APRES  /tenant/dashboard/home/info -> {after}')

    # Verif : /api/dashboard/home doit maintenant etre vide (front -> JSON par defaut)
    try:
        home = http_get('/api/dashboard/home', t)
        title = (home or {}).get('title') if isinstance(home, dict) else home
        print(f'VERIF  /dashboard/home title -> {title!r} (vide/None = home vanilla actif)')
    except SystemExit:
        print('VERIF  /dashboard/home -> reponse vide = home vanilla actif (attendu)')

    ok = not (isinstance(after, dict) and after.get('dashboardId'))
    print('\nOK : home dashboard tenant retire.' if ok else '\n!! toujours present, verifier.')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()

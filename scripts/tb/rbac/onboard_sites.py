#!/usr/bin/env python3
"""Onboarding site-customers (scaffold) — sous-chantier #1 du programme RBAC.

Cree 1 site-customer par installation (device profil 'pac hybride'), nomme depuis
nom_residence (fallback nom_alternatif, puis n de serie), suffixe le n de serie en
cas de collision de titre. Enregistre le mapping sur le device (attribut serveur
site_customer_id). NE deplace PAS les devices, NE pose PAS site_assigned.

DRY-RUN par defaut ; --apply pour ecrire.
Usage :
  TB_TOKEN=<jwt tenant-admin> python onboard_sites.py                    # dry-run
  TB_TOKEN=<jwt> python onboard_sites.py --apply                         # ECRIT en prod
  python onboard_sites.py --user je@yahtec.com --pwd '***'               # dry-run (login)
"""
import argparse
from collections import Counter
import _lib_rbac as tb

ATTR = 'site_customer_id'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='pac hybride')
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true', help='ECRIT en prod (defaut = dry-run)')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    apply = args.apply
    print(f'== Onboarding site-customers (scaffold) — {"APPLY (ecriture prod)" if apply else "DRY-RUN"} '
          f'— {tb.BASE_URL} ==\n')

    devices = tb.list_devices_by_profile(t, args.profile)
    print(f'{len(devices)} device(s) profil "{args.profile}"\n')

    # 1) titre de base par device (nom_residence > nom_alternatif > name) + collisions
    base = {}
    for d in devices:
        did = d['id']['id']
        a = tb.get_server_attrs(t, 'DEVICE', did, ['nom_residence', 'nom_alternatif'])
        base[did] = ((a.get('nom_residence') or a.get('nom_alternatif') or d['name']).strip()
                     or d['name'])
    freq = Counter(base.values())

    # 2) pour chaque device : titre final, resolution idempotente, pose du mapping
    created = reused = 0
    for d in devices:
        did = d['id']['id']
        title = base[did]
        if freq[title] > 1:
            title = f'{title} ({d["name"]})'
        existing = tb.get_server_attrs(t, 'DEVICE', did, [ATTR]).get(ATTR)
        if existing and tb.http_get(f'/api/customer/{existing}', t, allow_404=True):
            print(f'  {d["name"]:<14} REUSE  site-customer {existing}  ("{title}")')
            reused += 1
            continue
        cid = tb.ensure_customer(t, title, apply)  # cree si absent (apply) ; [DRY] sinon
        if cid:
            tb.set_server_attribute(t, did, ATTR, cid, apply)
            created += 1
        else:
            print(f'  {d["name"]:<14} [DRY]  creerait site + poserait {ATTR}  ("{title}")')

    print(f'\n== Termine == cree/maj={created} reuse={reused}'
          + ('' if apply else ' (dry-run — aucune ecriture)'))


if __name__ == '__main__':
    main()

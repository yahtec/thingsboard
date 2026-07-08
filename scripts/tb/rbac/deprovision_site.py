#!/usr/bin/env python3
"""De-provisionne un site (inverse de onboard_sites/provision) : device -> yahtec,
neutralise le marqueur site_assigned, retire les CanView vers son site-customer.
Le site-customer est CONSERVE (re-onboarding idempotent). DRY-RUN par defaut ; --apply pour ecrire.

  python deprovision_site.py --device 2610000001 --user je@yahtec.com --pwd '***'   # dry-run
  TB_TOKEN=<jwt> python deprovision_site.py --device 2610000001 --apply             # ecrit
"""
import argparse
import _lib_rbac as tb

YAHTEC_CID = '2e521d10-3e5d-11f1-bbfe-e1395562cba0'


def deprovision(t, device_name, apply):
    dev = tb.find_device_by_name(t, device_name)
    if not dev:
        print(f'  device introuvable : {device_name}')
        return
    did = dev['id']['id']
    cur = (dev.get('customerId') or {}).get('id')
    site_cid = tb.get_server_attrs(t, 'DEVICE', did, ['site_customer_id']).get('site_customer_id')
    print(f'== De-provision {device_name} (id={did}) ==')
    print(f'  customer actuel : {cur} ; site_customer_id : {site_cid or "(aucun)"}')

    # 1) neutralise le marqueur
    tb.set_server_attribute(t, did, 'site_assigned', False, apply)
    # 2) device -> yahtec
    if cur == YAHTEC_CID:
        print('  device deja sous yahtec')
    else:
        tb.assign_device_to_customer(t, did, YAHTEC_CID, apply)
    # 3) retrait des CanView pointant vers le site-customer
    if site_cid:
        rels = tb.find_relations_to(t, site_cid, tb.CANVIEW)
        if not rels:
            print(f'  aucune CanView vers le site-customer {site_cid}')
        for r in rels:
            party = r['from']['id']
            title = (tb.http_get(f'/api/customer/{party}', t, allow_404=True) or {}).get('title', party)
            print(f'  intervenant "{title}" ({party}) perd l\'acces au site')
            tb.delete_relation(t, party, site_cid, tb.CANVIEW, apply)
    else:
        print('  pas de site_customer_id -> aucune CanView a retirer')
    print('  site-customer CONSERVE (re-onboarding via onboard_sites reste possible)')
    print('== Termine ==' + ('' if apply else ' (dry-run — aucune ecriture)'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', required=True)
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    t = tb.token_or_login(args.user, args.pwd)
    print(f'== deprovision_site — {"APPLY (ecriture prod)" if args.apply else "DRY-RUN"} — {tb.BASE_URL} ==')
    deprovision(t, args.device, args.apply)


if __name__ == '__main__':
    main()

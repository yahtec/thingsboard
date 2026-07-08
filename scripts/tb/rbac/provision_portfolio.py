#!/usr/bin/env python3
"""Provisionne un portefeuille RBAC (customers-sites, parties PARTY/STAFF, relations) — idempotent.

DRY-RUN PAR DEFAUT (lecture seule). Ajouter --apply pour ecrire en prod.

Config JSON (cf demo.json) :
{
  "sites":   [{"title": "Site X", "device": "<deviceName>"}],
  "parties": [{"title": "Syndic Y", "role": "PARTY", "userEmail": "y@..", "canView": ["Site X"]}],
  "staff":   [{"title": "Tech Z",  "role": "STAFF", "userEmail": "z@..", "excluded": ["Site X"]}]
}

Usage :
  TB_TOKEN=<jwt tenant-admin> python provision_portfolio.py --config demo.json            # dry-run
  python provision_portfolio.py --config demo.json --user je@yahtec.com --pwd '***'        # dry-run
  python provision_portfolio.py --config demo.json --apply --new-user-pwd '***'            # ECRIT en prod
"""
import argparse, json, sys
import _lib_rbac as tb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true', help='ECRIT en prod (defaut = dry-run)')
    ap.add_argument('--new-user-pwd', default=None, help='mot de passe des users crees (requis avec --apply si users a creer)')
    args = ap.parse_args()

    with open(args.config, encoding='utf-8') as f:
        cfg = json.load(f)

    t = tb.token_or_login(args.user, args.pwd)
    apply = args.apply
    mode = 'APPLY (ecriture prod)' if apply else 'DRY-RUN (lecture seule)'
    print(f'== Provisioning portefeuille — {mode} — base {tb.BASE_URL} ==\n')

    # 1) Sites : customer-site par chaufferie + assignation du device
    print('[SITES]')
    site_ids = {}
    for s in cfg.get('sites', []):
        cid = tb.ensure_customer(t, s['title'], apply)
        site_ids[s['title']] = cid
        dev = tb.find_device_by_name(t, s['device'])
        if not dev:
            print(f'  !! device introuvable : {s["device"]} (site {s["title"]})')
            continue
        did = dev['id']['id']
        cur = (dev.get('customerId') or {}).get('id')
        if cur and cur == cid:
            print(f'  device deja assigne: {s["device"]} -> {s["title"]}')
            tb.set_server_attribute(t, did, 'site_assigned', True, apply)
        elif cid is None:
            print(f'  [DRY] assignerait device {s["device"]} -> {s["title"]} (customer a creer)')
        else:
            tb.assign_device_to_customer(t, did, cid, apply)
            tb.set_server_attribute(t, did, 'site_assigned', True, apply)

    config_site_ids = {v for v in site_ids.values() if v}

    # 2) Parties (PARTY) : customer + user + relations CanView
    print('\n[PARTIES]')
    for p in cfg.get('parties', []):
        cid = tb.ensure_customer(t, p['title'], apply)
        if cid is not None:
            tb.assign_dashboard_to_customer(t, cid, tb.KIOSK_DASH, apply)
        tb.ensure_user(t, p['userEmail'], 'CUSTOMER_USER', cid, p.get('role', 'PARTY'),
                       args.new_user_pwd, apply)
        desired = {site_ids[s] for s in p.get('canView', []) if site_ids.get(s)}
        for site_title in p.get('canView', []):
            sid = site_ids.get(site_title)
            if cid is None or sid is None:
                print(f'  [DRY] relation CanView : {p["title"]} -> {site_title} (customer(s) a creer)')
            else:
                tb.ensure_relation(t, cid, sid, tb.CANVIEW, apply)
        # revoke declaratif : retirer les CanView vers des sites du config non declares pour cette partie
        if cid is not None:
            existing = {r['to']['id'] for r in tb.find_relations_from(t, cid, tb.CANVIEW)}
            for stale in (existing & config_site_ids) - desired:
                tb.delete_relation(t, cid, stale, tb.CANVIEW, apply)

    # 3) Staff (STAFF) : customer + user + relations Excluded
    print('\n[STAFF]')
    for st in cfg.get('staff', []):
        cid = tb.ensure_customer(t, st['title'], apply)
        if cid is not None:
            tb.assign_dashboard_to_customer(t, cid, tb.KIOSK_DASH, apply)
        tb.ensure_user(t, st['userEmail'], 'CUSTOMER_USER', cid, st.get('role', 'STAFF'),
                       args.new_user_pwd, apply)
        desired = {site_ids[s] for s in st.get('excluded', []) if site_ids.get(s)}
        for site_title in st.get('excluded', []):
            sid = site_ids.get(site_title)
            if cid is None or sid is None:
                print(f'  [DRY] relation Excluded : {st["title"]} -> {site_title} (customer(s) a creer)')
            else:
                tb.ensure_relation(t, cid, sid, tb.EXCLUDED, apply)
        if cid is not None:
            existing = {r['to']['id'] for r in tb.find_relations_from(t, cid, tb.EXCLUDED)}
            for stale in (existing & config_site_ids) - desired:
                tb.delete_relation(t, cid, stale, tb.EXCLUDED, apply)

    print('\n== Termine ==' + ('' if apply else ' (aucune ecriture — dry-run)'))
    if apply and not args.new_user_pwd:
        print('NB: --new-user-pwd absent -> les users crees n\'ont pas de mot de passe (activation manuelle).', file=sys.stderr)


if __name__ == '__main__':
    main()

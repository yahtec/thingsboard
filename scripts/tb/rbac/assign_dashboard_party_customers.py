#!/usr/bin/env python3
"""Sweep : assigne le dashboard "Mes Installations" à tout party/staff-customer existant.

Sélection : customer (hors YAHTEC_CID) portant >=1 CUSTOMER_USER dont
additionalInfo.portfolioRole in {PARTY, STAFF}. Idempotent, dry-run par défaut.

  python assign_dashboard_party_customers.py --user je@yahtec.com --pwd '***'   # dry-run
  python assign_dashboard_party_customers.py --apply --user je@yahtec.com --pwd '***'
  python assign_dashboard_party_customers.py --self-test                        # offline
"""
import argparse, sys
import _lib_rbac as tb

YAHTEC_CID = '2e521d10-3e5d-11f1-bbfe-e1395562cba0'


def party_customer_ids(users, yahtec_cid):
    """Set des customer-ids portant un intervenant PARTY/STAFF (hors yahtec)."""
    out = set()
    for u in users:
        if u.get('authority') != 'CUSTOMER_USER':
            continue
        role = (u.get('additionalInfo') or {}).get('portfolioRole')
        if role not in ('PARTY', 'STAFF'):
            continue
        cid = (u.get('customerId') or {}).get('id')
        if cid and cid != yahtec_cid:
            out.add(cid)
    return out


def _self_test():
    users = [
        {'authority': 'CUSTOMER_USER', 'additionalInfo': {'portfolioRole': 'PARTY'}, 'customerId': {'id': 'c-party'}},
        {'authority': 'CUSTOMER_USER', 'additionalInfo': {'portfolioRole': 'STAFF'}, 'customerId': {'id': 'c-staff'}},
        {'authority': 'TENANT_ADMIN', 'additionalInfo': {'portfolioRole': 'ADMIN_OPS'}, 'customerId': {'id': '13814000-1dd2-11b2-8080-808080808080'}},
        {'authority': 'CUSTOMER_USER', 'additionalInfo': {'portfolioRole': 'PARTY'}, 'customerId': {'id': YAHTEC_CID}},
        {'authority': 'CUSTOMER_USER', 'additionalInfo': {'portfolioRole': 'PARTY'}, 'customerId': None},
        {'authority': 'CUSTOMER_USER', 'additionalInfo': {}, 'customerId': {'id': 'c-legacy'}},
    ]
    got = party_customer_ids(users, YAHTEC_CID)
    assert got == {'c-party', 'c-staff'}, got
    print('self-test OK :', sorted(got))


def _all_users(t):
    out, page = [], 0
    while True:
        d = tb.http_get(f'/api/users?{tb._q(pageSize=200, page=page)}', t)
        out.extend((d or {}).get('data', []))
        if not (d or {}).get('hasNext'):
            break
        page += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        _self_test()
        return
    t = tb.token_or_login(args.user, args.pwd)
    apply = args.apply
    print(f'== Sweep dashboard party-customers — {"APPLY" if apply else "DRY-RUN"} — {tb.BASE_URL} ==\n')
    cids = party_customer_ids(_all_users(t), YAHTEC_CID)
    print(f'{len(cids)} party/staff-customer(s) cible(s)\n')
    for cid in sorted(cids):
        tb.assign_dashboard_to_customer(t, cid, tb.KIOSK_DASH, apply)
    print('\n== Termine ==' + ('' if apply else ' (dry-run — aucune ecriture)'))


if __name__ == '__main__':
    main()

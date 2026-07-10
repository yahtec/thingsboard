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
        dev = tb.find_device_by_name(t, s['device'])
        if not dev:
            # Meme sans device, le customer-site du titre config doit exister pour que
            # les CanView/Excluded en aval (PARTIES/STAFF) puissent s'y accrocher.
            site_ids[s['title']] = tb.ensure_customer(t, s['title'], apply)
            print(f'  !! device introuvable : {s["device"]} (site {s["title"]})')
            continue
        did = dev['id']['id']

        # I17 : si le device porte deja un site_customer_id pointant un customer
        # EXISTANT, on le reutilise tel quel — pas de creation/assignation vers le
        # customer titre config, qui se battrait sinon avec onboard_sites.py/migrate a
        # chaque re-run (flip-flop sur le meme device).
        linked_cid = tb.get_server_attrs(t, 'DEVICE', did, ['site_customer_id']).get('site_customer_id')
        linked_customer = tb.http_get(f'/api/customer/{linked_cid}', t, allow_404=True, allow_400=True) \
            if linked_cid else None
        if linked_customer:
            cid = linked_cid
            site_ids[s['title']] = cid
            real_title = linked_customer.get('title')
            note = '' if real_title == s['title'] else f' (titre config "{s["title"]}" != titre reel "{real_title}")'
            print(f'  site {s["title"]:<20} REUTILISE via site_customer_id : {cid}{note}')
            cur = (dev.get('customerId') or {}).get('id')
            if cur != cid:
                # M-ordre : marqueur AVANT assignation (miroir deprovision_site.py) —
                # une telemetrie/panne dans la fenetre ne doit jamais trouver
                # site_assigned=false alors que le device est en cours de bascule.
                tb.set_server_attribute(t, did, 'site_assigned', True, apply)
                tb.assign_device_to_customer(t, did, cid, apply)
            else:
                tb.set_server_attribute(t, did, 'site_assigned', True, apply)
            continue

        cid = tb.ensure_customer(t, s['title'], apply)
        site_ids[s['title']] = cid
        cur = (dev.get('customerId') or {}).get('id')
        if cur and cur == cid:
            print(f'  device deja assigne: {s["device"]} -> {s["title"]}')
            tb.set_server_attribute(t, did, 'site_assigned', True, apply)
            tb.set_server_attribute(t, did, 'site_customer_id', cid, apply)  # I17 : sync
        elif cid is None:
            print(f'  [DRY] assignerait device {s["device"]} -> {s["title"]} (customer a creer)')
            # M-dry-run : enumerer aussi ce que --apply ferait ensuite (le dry-run se
            # limitait avant a une seule ligne, en omettant les ecritures d'attributs).
            print(f'  [DRY] poserait attr SERVER site_assigned=True sur device {did}')
            print(f'  [DRY] poserait attr SERVER site_customer_id=<nouveau customer> sur device {did}')
        else:
            # M-ordre : marqueur AVANT assignation.
            tb.set_server_attribute(t, did, 'site_assigned', True, apply)
            tb.assign_device_to_customer(t, did, cid, apply)
            tb.set_server_attribute(t, did, 'site_customer_id', cid, apply)  # I17 : sync

    config_site_ids = {v for v in site_ids.values() if v}
    mismatches = []  # I18 : emails ensure_user a detecte sous un customerId different
    unknown_sites = []  # I16 : titres de site references (canView/excluded) absents de cfg['sites']

    # 2) Parties (PARTY) : customer + user + relations CanView
    print('\n[PARTIES]')
    for p in cfg.get('parties', []):
        cid = tb.ensure_customer(t, p['title'], apply)
        if cid is not None:
            tb.assign_dashboard_to_customer(t, cid, tb.KIOSK_DASH, apply)
        uid = tb.ensure_user(t, p['userEmail'], 'CUSTOMER_USER', cid, p.get('role', 'PARTY'),
                              args.new_user_pwd, apply)
        if uid == tb.CUSTOMER_MISMATCH:
            mismatches.append(p['userEmail'])
        desired = {site_ids[s] for s in p.get('canView', []) if site_ids.get(s)}
        for site_title in p.get('canView', []):
            sid = site_ids.get(site_title)
            if sid is None:
                # I16 : titre de site absent de cfg['sites'] (typo probable). En apply,
                # ne JAMAIS le confondre avec un simple "customer a creer" — c'est une
                # erreur dure a lister et faire echouer le run, pas un [DRY] silencieux.
                if apply:
                    print(f'  !! site inconnu : {p["title"]} -> {site_title} (CanView)')
                    unknown_sites.append(f'{p["title"]} -> {site_title} (CanView)')
                else:
                    print(f'  [DRY] relation CanView : {p["title"]} -> {site_title} '
                          f'(site inconnu — a creer dans cfg[sites] ou typo ?)')
                continue
            if cid is None:
                print(f'  [DRY] relation CanView : {p["title"]} -> {site_title} (customer a creer)')
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
        uid = tb.ensure_user(t, st['userEmail'], 'CUSTOMER_USER', cid, st.get('role', 'STAFF'),
                              args.new_user_pwd, apply)
        if uid == tb.CUSTOMER_MISMATCH:
            mismatches.append(st['userEmail'])
        desired = {site_ids[s] for s in st.get('excluded', []) if site_ids.get(s)}
        for site_title in st.get('excluded', []):
            sid = site_ids.get(site_title)
            if sid is None:
                # I16 : symetrique du bloc CanView ci-dessus.
                if apply:
                    print(f'  !! site inconnu : {st["title"]} -> {site_title} (Excluded)')
                    unknown_sites.append(f'{st["title"]} -> {site_title} (Excluded)')
                else:
                    print(f'  [DRY] relation Excluded : {st["title"]} -> {site_title} '
                          f'(site inconnu — a creer dans cfg[sites] ou typo ?)')
                continue
            if cid is None:
                print(f'  [DRY] relation Excluded : {st["title"]} -> {site_title} (customer a creer)')
            else:
                tb.ensure_relation(t, cid, sid, tb.EXCLUDED, apply)
        if cid is not None:
            existing = {r['to']['id'] for r in tb.find_relations_from(t, cid, tb.EXCLUDED)}
            for stale in (existing & config_site_ids) - desired:
                tb.delete_relation(t, cid, stale, tb.EXCLUDED, apply)

    print('\n== Termine ==' + ('' if apply else ' (aucune ecriture — dry-run)'))
    if apply and not args.new_user_pwd:
        print('NB: --new-user-pwd absent -> les users crees n\'ont pas de mot de passe (activation manuelle).', file=sys.stderr)

    # I16 + I18 : un seul bloc d'exit non-zero combine, pour que ni l'un ni l'autre ne
    # masque le rapport de l'autre (les deux listes sont independantes et cumulables).
    had_errors = False
    if unknown_sites:
        print(f'\n!!! {len(unknown_sites)} site(s) inconnu(s) reference(s) en config (typo ?) '
              f'— aucune relation creee :')
        for m in unknown_sites:
            print(f'  - {m}')
        had_errors = True

    if mismatches:
        # I18 : customerId immuable cote TB -> pas de correction automatique possible ici,
        # juste un signal fort pour que l'operateur traite (suppression+recreation manuelle).
        print(f'\n!!! {len(mismatches)} user(s) avec customerId en conflit (email deja '
              f'utilise sous un autre customer ; customerId immuable cote TB) :')
        for e in mismatches:
            print(f'  - {e}')
        had_errors = True

    if had_errors:
        sys.exit(1)


if __name__ == '__main__':
    main()

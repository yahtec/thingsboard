#!/usr/bin/env python3
"""Migration LEGACY -> RBAC (sous-chantier #2).

A) Deplace chaque device pac hybride vers son site-customer (attribut site_customer_id) + site_assigned=true.
B) Pour chaque CUSTOMER_USER sous yahtec avec attribut chaufferies non vide : party-customer
   "Party — {email}" + CanView vers les site-customers de ses chaufferies + migre le user en PARTY
   sous ce party-customer (delete+recreate ; customerId TB immuable ; reset mdp).
C) Supprime les comptes nus at@test.com + ac+user@yahtec.com.
D) ac@yahtec.com -> additionalInfo.portfolioRole=ADMIN_OPS (update en place).

DRY-RUN par defaut ; --apply pour ecrire ; --new-user-pwd requis avec --apply (recreate users).
"""
import argparse, json, os, sys, urllib.parse
import _lib_rbac as tb

YAHTEC_CID = '2e521d10-3e5d-11f1-bbfe-e1395562cba0'
KIOSK_DASH = '0964da30-3e56-11f1-bbfe-e1395562cba0'
PROFILE = 'pac hybride'
USER_ATTR_KEYS = ['chaufferies', 'droit_acces', 'societe',
                  'access_rapport', 'access_retroview', 'access_spherys', 'expiration_ts']
DELETE_BARE = ['at@test.com', 'ac+user@yahtec.com']
KIOSK_INFO = {'homeDashboardId': KIOSK_DASH, 'homeDashboardHideToolbar': True,
              'defaultDashboardId': KIOSK_DASH, 'defaultDashboardFullscreen': True}


def _users_under(t, customer_id):
    """CUSTOMER_USER du tenant sous un customer donne (via /api/users pagine)."""
    out, page = [], 0
    while True:
        d = tb.http_get(f'/api/users?{tb._q(pageSize=200, page=page)}', t)
        for u in (d or {}).get('data', []):
            if (u.get('customerId') or {}).get('id') == customer_id and u.get('authority') == 'CUSTOMER_USER':
                out.append(u)
        if not (d or {}).get('hasNext'):
            break
        page += 1
    return out


def _migrate_user(t, u, pwd, apply):
    email = u['email']
    uid = u['id']['id']
    attrs = tb.get_server_attrs(t, 'USER', uid, USER_ATTR_KEYS)
    chauff = attrs.get('chaufferies') or []
    if isinstance(chauff, str):
        chauff = json.loads(chauff)
    if not chauff:
        print(f'  SKIP (pas de chaufferies) : {email}')
        return
    droit = attrs.get('droit_acces') or 'lecture'
    role = 'ADMIN_OPS' if droit == 'admin' else 'PARTY'
    print(f'  MIGRE {email} : droit={droit} -> {role}, {len(chauff)} chaufferie(s)')
    party_cid = tb.ensure_customer(t, f'Party — {email}', apply)
    for dev_id in chauff:
        site_cid = tb.get_server_attrs(t, 'DEVICE', dev_id, ['site_customer_id']).get('site_customer_id')
        if not site_cid:
            print(f'    !! device {dev_id} sans site_customer_id (onboarding #1 manquant) -> CanView ignore')
            continue
        if party_cid:
            tb.ensure_relation(t, party_cid, site_cid, tb.CANVIEW, apply)
        else:
            print(f'    [DRY] CanView -> site {site_cid}')
    if not apply:
        print(f'    [DRY] recreerait {email} sous party-customer (role={role}) + re-appliquerait attributs')
        return
    fn, ln = u.get('firstName'), u.get('lastName')
    keep = {k: attrs[k] for k in USER_ATTR_KEYS if k in attrs}
    # Filet de securite (migration destructive) : dumper la donnee de recuperation AVANT le delete.
    recovery = {'email': email, 'firstName': fn, 'lastName': ln,
                'party_customer_id': party_cid, 'portfolioRole': role, 'server_attrs': keep}
    bdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migration-backup')
    os.makedirs(bdir, exist_ok=True)
    bpath = os.path.join(bdir, email.replace('/', '_').replace('@', '_at_') + '.json')
    with open(bpath, 'w', encoding='utf-8') as f:
        json.dump(recovery, f, ensure_ascii=False, indent=2)
    try:
        tb.http_delete(f'/api/user/{uid}', t)
        body = {'email': email, 'authority': 'CUSTOMER_USER',
                'customerId': {'id': party_cid, 'entityType': 'CUSTOMER'},
                'additionalInfo': dict(KIOSK_INFO, portfolioRole=role)}
        if fn:
            body['firstName'] = fn
        if ln:
            body['lastName'] = ln
        created = tb.http_post('/api/user?sendActivationMail=false', body, t)
        new_uid = created['id']['id']
        link = tb.http_get_text(f'/api/user/{new_uid}/activationLink', t)
        atok = urllib.parse.parse_qs(urllib.parse.urlparse(link.strip()).query).get('activateToken', [None])[0]
        if atok:
            tb.http_post('/api/noauth/activate', {'activateToken': atok, 'password': pwd}, t)
            pwd_note = 'mdp reset'
        else:
            pwd_note = f'!! ACTIVATION MANUELLE REQUISE (lien: {link.strip()})'
        if keep:
            tb.save_server_attrs(t, 'USER', new_uid, keep, apply)
        print(f'    RECREE {email} sous {party_cid} (role={role}), {pwd_note}, attributs re-appliques')
    except BaseException as e:
        print(f'    !!!! ECHEC MIGRATION {email} APRES DELETE — user potentiellement supprime sans remplacement.')
        print(f'         Donnee de recuperation conservee dans : {bpath}')
        print(f'         Erreur : {e}')
        raise
    # Succes : retirer le backup de recuperation (echec de suppression sans gravite -> il persiste)
    try:
        os.remove(bpath)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--new-user-pwd', default=None)
    args = ap.parse_args()
    t = tb.token_or_login(args.user, args.pwd)
    apply = args.apply
    if apply and not args.new_user_pwd:
        sys.exit('--new-user-pwd requis avec --apply (recreate users)')
    print(f'== Migration LEGACY -> RBAC — {"APPLY (ecriture prod)" if apply else "DRY-RUN"} — {tb.BASE_URL} ==\n')

    print('[A] Deplacement devices pac hybride -> site-customers')
    for d in tb.list_devices_by_profile(t, PROFILE):
        did = d['id']['id']
        site_cid = tb.get_server_attrs(t, 'DEVICE', did, ['site_customer_id']).get('site_customer_id')
        if not site_cid:
            print(f'  !! {d["name"]} sans site_customer_id -> skip (lancer onboard_sites.py #1)')
            continue
        if (d.get('customerId') or {}).get('id') == site_cid:
            print(f'  {d["name"]:<14} deja sous son site-customer')
        else:
            tb.assign_device_to_customer(t, did, site_cid, apply)
        tb.set_server_attribute(t, did, 'site_assigned', True, apply)

    print('\n[B] Migration users LEGACY scopes -> PARTY')
    for u in _users_under(t, YAHTEC_CID):
        _migrate_user(t, u, args.new_user_pwd, apply)

    print('\n[C] Suppression comptes nus')
    for email in DELETE_BARE:
        u = tb.find_user_by_email(t, email)
        if not u:
            print(f'  absent : {email}')
        elif apply:
            tb.http_delete(f'/api/user/{u["id"]["id"]}', t)
            print(f'  SUPPRIME : {email}')
        else:
            print(f'  [DRY] supprimerait : {email}')

    print('\n[D] ac@yahtec.com -> ADMIN_OPS (update en place)')
    ac = tb.find_user_by_email(t, 'ac@yahtec.com')
    if not ac:
        print('  ac@ introuvable')
    elif (ac.get('additionalInfo') or {}).get('portfolioRole') == 'ADMIN_OPS':
        print('  ac@ deja ADMIN_OPS')
    elif apply:
        ac['additionalInfo'] = dict(ac.get('additionalInfo') or {}, portfolioRole='ADMIN_OPS')
        tb.http_post('/api/user', ac, t)
        print('  ac@ -> portfolioRole=ADMIN_OPS')
    else:
        print('  [DRY] ac@ -> portfolioRole=ADMIN_OPS')

    print('\n== Termine ==' + ('' if apply else ' (dry-run — aucune ecriture)'))


if __name__ == '__main__':
    main()

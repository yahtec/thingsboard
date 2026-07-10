#!/usr/bin/env python3
"""Cree un compte de SERVICE TENANT_ADMIN headless pour tb-notify (remplace l'usage
du compte humain af@ pour les appels API du service). Idempotent (skip si l'email existe).
Dry-run par defaut ; --apply pour ecrire. Le mdp genere est affiche sur --apply
(a poser dans le .env serveur : TB_PASS). Reste TENANT_ADMIN (limite CE, pas de PAT)."""
import argparse
import os
import secrets
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_rbac as tb  # noqa: E402

DEFAULT_EMAIL = 'svc-tbnotify@yahtec.com'
DESCRIPTION = 'tb-notify service account (headless, TENANT_ADMIN)'


def gen_password(nbytes=24):
    """Mot de passe fort URL-safe (token_urlsafe(24) ~ 32 chars)."""
    return secrets.token_urlsafe(nbytes)


def build_body(email):
    """Corps de creation d'un TENANT_ADMIN de service (headless : pas de customerId)."""
    return {
        'email': email,
        'authority': 'TENANT_ADMIN',
        'additionalInfo': {'description': DESCRIPTION},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--email', default=DEFAULT_EMAIL)
    ap.add_argument('--new-pwd', default=None, help='mdp du compte (genere si absent)')
    ap.add_argument('--user', default='je@yahtec.com', help='admin qui cree (ou TB_TOKEN)')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    existing = tb.find_user_by_email(t, args.email)
    if existing:
        uid = existing['id']['id']
        info = tb.get_activation_link_info(t, uid)
        if info is None:
            print(f'compte deja existant et actif : {args.email} (uid {uid}) -> rien a faire')
            return
        # I15 : le POST /api/user initial avait reussi mais l'activation avait echoue
        # (reseau, mdp hors policy...) -> se contenter de "rien a faire" ici laissait le
        # compte inactif sans mot de passe pour toujours.
        print(f'compte existant MAIS PAS ACTIVE : {args.email} (uid {uid})')
        if not args.apply:
            print('  [DRY-RUN] relancerait l\'activation avec --apply (--new-pwd ou mdp genere).')
            return
        pwd = args.new_pwd or gen_password()
        tok = urllib.parse.parse_qs(urllib.parse.urlparse(info['value'].strip()).query).get(
            'activateToken', [None])[0]
        if not tok:
            sys.exit(f'ECHEC activation (lien inattendu) : {info["value"]}')
        tb.http_post('/api/noauth/activate', {'activateToken': tok, 'password': pwd}, t)
        print(f'REACTIVE : {args.email} (uid {uid})')
        print('  -> poser dans le .env serveur :')
        print(f'     TB_USER={args.email}')
        print(f'     TB_PASS={pwd}')
        return
    if not args.apply:
        print(f'[DRY-RUN] creerait TENANT_ADMIN {args.email} (mdp genere, non affiche en dry-run).')
        print('  Ajouter --apply pour creer.')
        return
    pwd = args.new_pwd or gen_password()
    created = tb.http_post('/api/user?sendActivationMail=false', build_body(args.email), t)
    uid = created['id']['id']
    link = tb.http_get_text(f'/api/user/{uid}/activationLink', t)
    tok = urllib.parse.parse_qs(urllib.parse.urlparse(link.strip()).query).get('activateToken', [None])[0]
    if not tok:
        sys.exit(f'ECHEC activation (lien inattendu) : {link}')
    tb.http_post('/api/noauth/activate', {'activateToken': tok, 'password': pwd}, t)
    print(f'CREE + ACTIVE : {args.email} (uid {uid})')
    print('  -> poser dans le .env serveur :')
    print(f'     TB_USER={args.email}')
    print(f'     TB_PASS={pwd}')


if __name__ == '__main__':
    main()

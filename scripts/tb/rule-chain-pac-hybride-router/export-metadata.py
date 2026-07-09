#!/usr/bin/env python3
"""Exporte la metadata de la rule chain PAC Hybride Router vers un JSON versionné
(artefact de sécurité, diff = revue de dérive). Dry-run (stdout) par défaut ; --write pour écrire."""
import argparse, json, os, sys, urllib.request, urllib.error

RC_ID = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL = os.environ.get('TB_BASE_URL', 'https://thingsboard.tsmart.fr')
SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metadata.snapshot.json')


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'}, method='GET')
    with urllib.request.urlopen(r, timeout=60) as o:
        return json.loads(o.read().decode('utf-8'))


def token_or_login(user, pwd):
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if not pwd:
        sys.exit('Fournir --pwd ou definir TB_TOKEN')
    b = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def canonical_json(meta):
    """Rend la metadata en JSON stable : connexions triées (ordre non signifiant), clés triées."""
    m = dict(meta)
    if isinstance(m.get('connections'), list):
        m['connections'] = sorted(m['connections'],
                                  key=lambda c: (c.get('fromIndex'), c.get('toIndex'), c.get('type')))
    return json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    t = token_or_login(args.user, args.pwd)
    out = canonical_json(http_get(f'/api/ruleChain/{RC_ID}/metadata', t))
    if args.write:
        with open(SNAP, 'w', encoding='utf-8') as f:
            f.write(out + '\n')
        print(f'écrit {SNAP} ({len(out)} octets)')
    else:
        print(out)
        print(f'\n[DRY-RUN] --write pour écrire {SNAP}', file=sys.stderr)


if __name__ == '__main__':
    main()

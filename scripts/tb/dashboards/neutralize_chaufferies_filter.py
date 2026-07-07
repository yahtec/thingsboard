#!/usr/bin/env python3
"""Neutralise le filtre client 'chaufferies' d'un dashboard : l'expression
fetch(...keys=chaufferies...) resolue en Set|null est remplacee par
Promise.resolve(null). Idempotent. Dry-run par defaut ; --apply pour ecrire.

Usage: TB_TOKEN=... python neutralize_chaufferies_filter.py <dashboardId> [--apply]
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rbac'))
import _lib_rbac as tb

# Remplace toute expression fetch(...) chainee (.then/.catch) qui contient
# 'keys=chaufferies' par Promise.resolve(null). Regex bornee au fetch( ... )
# jusqu'au point-virgule ou a la fermeture de l'affectation.
FETCH_RE = re.compile(
    r"fetch\(\s*['\"][^'\"]*keys=chaufferies[^;]*?\.catch\([^;]*?\)",
    re.DOTALL)
REPLACEMENT = 'Promise.resolve(null)'

def neutralize(text):
    """Retourne (nouveau_texte, nb_remplacements)."""
    return FETCH_RE.subn(REPLACEMENT, text)

def walk(obj, counter):
    """Applique la neutralisation sur toutes les chaines JSON du dashboard."""
    if isinstance(obj, str):
        new, n = neutralize(obj)
        counter[0] += n
        return new
    if isinstance(obj, list):
        return [walk(x, counter) for x in obj]
    if isinstance(obj, dict):
        return {k: walk(v, counter) for k, v in obj.items()}
    return obj

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dashboard_id')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--user', default=os.environ.get('TB_USER', 'je@yahtec.com'))
    ap.add_argument('--pwd', default=os.environ.get('TB_PWD'))
    args = ap.parse_args()
    t = tb.token_or_login(args.user, args.pwd)

    d = tb.http_get(f'/api/dashboard/{args.dashboard_id}', t)
    before = json.dumps(d.get('configuration', {}), ensure_ascii=False)
    n_before_fetch = before.count('keys=chaufferies')
    counter = [0]
    d['configuration'] = walk(d.get('configuration', {}), counter)
    after = json.dumps(d.get('configuration', {}), ensure_ascii=False)
    n_after_fetch = after.count('keys=chaufferies')

    print(f'dashboard {args.dashboard_id}')
    print(f'  occurrences "keys=chaufferies" AVANT={n_before_fetch}  APRES={n_after_fetch}')
    print(f'  expressions fetch neutralisees = {counter[0]}')
    if counter[0] == 0:
        print('  (rien a faire : deja neutralise ou pattern non trouve — VERIFIER a la main si AVANT>0)')
    if not args.apply:
        print('DRY-RUN : rien ecrit. --apply pour appliquer.')
        return
    tb.http_post('/api/dashboard', d, t)
    print('  APPLIQUE.')

if __name__ == '__main__':
    main()

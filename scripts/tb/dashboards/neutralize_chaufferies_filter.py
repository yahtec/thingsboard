#!/usr/bin/env python3
"""Neutralise le filtre client 'chaufferies' d'un dashboard : l'expression
fetch(...keys=chaufferies...) resolue en Set|null est remplacee par
Promise.resolve(null). Idempotent. Dry-run par defaut ; --apply pour ecrire.

Usage: TB_TOKEN=... python neutralize_chaufferies_filter.py <dashboardId> [--apply]
       python neutralize_chaufferies_filter.py --self-test
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rbac'))
import _lib_rbac as tb

# Remplace toute expression fetch(...) chainee (.then/.catch) qui contient
# 'keys=chaufferies' par Promise.resolve(null). Regex bornee au fetch( ... )
# jusqu'au point-virgule qui termine l'affectation.
# NB : le prefixe utilise [^;]*? (et non [^'"]*) entre la quote d'ouverture et
# 'keys=chaufferies' pour traverser la concatenation de chaines JS
# ('...'+uid+'...keys=chaufferies') qu'utilise le widget reel, tout en restant
# borne par ';' pour ne pas deborder sur une autre instruction fetch(...) qui
# la precederait dans la meme chaine JSON (verifie par --self-test).
FETCH_RE = re.compile(
    r"fetch\(\s*['\"][^;]*?keys=chaufferies.*?\.catch\(.*?\)(?=\s*;)",
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

# Sample JS extrait du widget reel (structure .then/.then/.catch avec ';'
# final) : sert de fixture hors-ligne pour --self-test, sans toucher au reseau.
SELFTEST_SAMPLE = (
    "var p = fetch('/api/plugins/telemetry/USER/'+uid+'/values/attributes/SERVER_SCOPE?keys=chaufferies', { headers: H() })\n"
    "  .then(function(rr){ return rr.ok ? rr.json() : []; })\n"
    "  .then(function(arr){ var v = (arr||[]).filter(function(a){return a.key==='chaufferies';})[0];\n"
    "     if (!v) return null; var list = v.value; if (typeof list==='string'){try{list=JSON.parse(list);}catch(e){list=[];}}\n"
    "     if (!Array.isArray(list)||!list.length) return null; var s=new Set(); list.forEach(function(x){s.add(String(x));}); return s; })\n"
    "  .catch(function(){ return null; });\n")

def self_test():
    """Verifie neutralize() hors-ligne (aucun appel reseau). Leve AssertionError si KO."""
    out1, n1 = neutralize(SELFTEST_SAMPLE)
    assert n1 == 1, f'attendu 1 remplacement sur le sample, obtenu {n1}'
    assert 'Promise.resolve(null)' in out1, 'Promise.resolve(null) absent du resultat'
    assert 'keys=chaufferies' not in out1, 'keys=chaufferies encore present apres neutralisation'

    out2, n2 = neutralize(out1)
    assert n2 == 0, f'non idempotent : {n2} remplacement(s) supplementaire(s) sur une 2e passe'

    _, n3 = neutralize("fetch('x?keys=other').catch(function(){});")
    assert n3 == 0, 'ne doit pas neutraliser un fetch keys=other non lie'

    print('SELF-TEST OK')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dashboard_id', nargs='?', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--self-test', action='store_true', help='teste neutralize() hors-ligne et quitte (aucun reseau)')
    ap.add_argument('--user', default=os.environ.get('TB_USER', 'je@yahtec.com'))
    ap.add_argument('--pwd', default=os.environ.get('TB_PWD'))
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.dashboard_id:
        ap.error('dashboard_id est requis (sauf en mode --self-test)')

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

    if n_before_fetch > 0 and counter[0] == 0:
        # Le motif cible est present mais la regex n'a rien remplace : mieux
        # vaut abandonner que POSTer un dashboard inchange en pretendant
        # avoir applique la neutralisation.
        print('  ERREUR : "keys=chaufferies" present mais aucune expression neutralisee '
              '(FETCH_RE ne matche pas ce JS) — ABANDON, rien ecrit.', file=sys.stderr)
        sys.exit(3)

    if counter[0] == 0:
        print('  (rien a faire : deja neutralise)')

    if not args.apply:
        print('DRY-RUN : rien ecrit. --apply pour appliquer.')
        return
    tb.http_post('/api/dashboard', d, t)
    print('  APPLIQUE.')

if __name__ == '__main__':
    main()

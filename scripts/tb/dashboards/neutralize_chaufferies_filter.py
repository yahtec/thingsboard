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
# jusqu'a la fermeture complete du .catch(function(...){...}) final.
# NB : le prefixe utilise [^;]*? (et non [^'"]*) entre la quote d'ouverture et
# 'keys=chaufferies' pour traverser la concatenation de chaines JS
# ('...'+uid+'...keys=chaufferies') qu'utilise le widget reel.
# NB2 : la queue ne s'arrete plus au premier ')' suivi de ';' (ancien bug :
# un catch dont le corps contient un appel-puis-';' interne, ex.
# function(){ console.log('e'); return null; }, n'etait matche que
# partiellement et le replace laissait un fragment JS pendouillant). La
# queue matche desormais tout le callback function(...){ ... } du catch en
# excluant les accolades imbriquees ([^{}]*) : elle consomme donc le corps
# du catch en entier quand il est plat, et echoue proprement (0 match, texte
# inchange) si le corps contient des accolades imbriquees (if/for/etc.),
# plutot que de produire un JS corrompu (verifie par --self-test).
FETCH_RE = re.compile(
    r"fetch\(\s*['\"][^;]*?keys=chaufferies.*?\.catch\(function\s*\([^)]*\)\s*\{[^{}]*\}\s*\)",
    re.DOTALL)
REPLACEMENT = 'Promise.resolve(null)'

def neutralize(text):
    """Retourne (nouveau_texte, nb_remplacements)."""
    return FETCH_RE.subn(REPLACEMENT, text)

def walk(obj, counter, spans=None):
    """Applique la neutralisation sur toutes les chaines JSON du dashboard.
    Si spans est une liste, y accumule le texte exact (avant remplacement)
    de chaque expression neutralisee, pour affichage en dry-run (l'operateur
    peut ainsi verifier a l'oeil ce qui est effectivement remplace, les
    compteurs seuls ayant ete juges insuffisants)."""
    if isinstance(obj, str):
        if spans is not None:
            spans.extend(m.group(0) for m in FETCH_RE.finditer(obj))
        new, n = neutralize(obj)
        counter[0] += n
        return new
    if isinstance(obj, list):
        return [walk(x, counter, spans) for x in obj]
    if isinstance(obj, dict):
        return {k: walk(v, counter, spans) for k, v in obj.items()}
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

# Variante du sample ci-dessus avec un corps de catch NON trivial : un
# appel de fonction suivi d'un ';' interne (console.log('e');). Reproduit le
# bug corrige par Fix A, ou l'ancienne regex (tete .*? bornee au premier ')'
# suivi de ';') coupait le catch en plein milieu et laissait un fragment JS
# pendouillant ('; return null; });') dans le dashboard neutralise.
SELFTEST_SAMPLE_CATCH_MODERATE = SELFTEST_SAMPLE.replace(
    '.catch(function(){ return null; });',
    ".catch(function(){ console.log('e'); return null; });")

# Variante avec un corps de catch contenant des accolades imbriquees
# (if(x){...}) : la nouvelle regex ([^{}]* dans la queue) ne peut pas la
# consommer entierement et doit donc echouer proprement (0 match, texte
# inchange) plutot que produire un remplacement partiel/corrompu.
SELFTEST_SAMPLE_CATCH_NESTED = SELFTEST_SAMPLE.replace(
    '.catch(function(){ return null; });',
    '.catch(function(){ if(x){ y(); } return null; });')

def self_test():
    """Verifie neutralize() hors-ligne (aucun appel reseau). Leve AssertionError si KO."""
    # Cas 1 : catch trivial -> neutralisation complete + idempotence.
    out1, n1 = neutralize(SELFTEST_SAMPLE)
    assert n1 == 1, f'attendu 1 remplacement sur le sample, obtenu {n1}'
    assert 'Promise.resolve(null)' in out1, 'Promise.resolve(null) absent du resultat'
    assert 'keys=chaufferies' not in out1, 'keys=chaufferies encore present apres neutralisation'

    out2, n2 = neutralize(out1)
    assert n2 == 0, f'non idempotent : {n2} remplacement(s) supplementaire(s) sur une 2e passe'

    # Cas 2 : catch avec appel-puis-';' interne -> doit etre consomme EN
    # ENTIER. Si la regex coupe prematurement (ancien bug), le fragment
    # 'console.log' survit dans le resultat -> JS corrompu.
    assert SELFTEST_SAMPLE_CATCH_MODERATE != SELFTEST_SAMPLE, 'fixture catch-moderate mal construite (replace no-op)'
    out3, n3 = neutralize(SELFTEST_SAMPLE_CATCH_MODERATE)
    assert n3 == 1, f'attendu 1 remplacement sur le sample catch-moderate, obtenu {n3}'
    assert 'console.log' not in out3, ("fragment \"console.log\" encore present apres neutralisation "
                                       "(catch coupe prematurement -> JS corrompu)")

    # Cas 3 : catch avec accolades imbriquees -> doit echouer proprement
    # (0 match, texte totalement inchange), jamais de remplacement partiel.
    assert SELFTEST_SAMPLE_CATCH_NESTED != SELFTEST_SAMPLE, 'fixture catch-nested mal construite (replace no-op)'
    out4, n4 = neutralize(SELFTEST_SAMPLE_CATCH_NESTED)
    assert n4 == 0, f'attendu 0 remplacement sur le sample catch-nested (accolades imbriquees), obtenu {n4}'
    assert out4 == SELFTEST_SAMPLE_CATCH_NESTED, 'texte modifie alors que 0 remplacement attendu (corruption)'

    # Cas 4 : fetch non lie (keys=other) -> jamais touche.
    _, n5 = neutralize("fetch('x?keys=other').catch(function(){});")
    assert n5 == 0, 'ne doit pas neutraliser un fetch keys=other non lie'

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
    spans = []
    d['configuration'] = walk(d.get('configuration', {}), counter, spans)
    after = json.dumps(d.get('configuration', {}), ensure_ascii=False)
    n_after_fetch = after.count('keys=chaufferies')

    print(f'dashboard {args.dashboard_id}')
    print(f'  occurrences "keys=chaufferies" AVANT={n_before_fetch}  APRES={n_after_fetch}')
    print(f'  expressions fetch neutralisees = {counter[0]}')

    if not args.apply and spans:
        # Dry-run : affiche le texte exact matche (avant remplacement) pour
        # que l'operateur puisse le relire, les compteurs seuls ne suffisant
        # pas a garantir l'absence de coupe partielle.
        for i, s in enumerate(spans, 1):
            snippet = s if len(s) <= 300 else s[:300] + '...'
            print(f'--- span neutralise {i}/{len(spans)} ---')
            print(snippet)

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

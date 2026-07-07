#!/usr/bin/env python3
"""Neutralise le filtre client 'chaufferies' d'un dashboard, SANS toucher a la
structure JS du widget.

Approche (balance-neutral, zero risque de corruption) : on renomme la CLE d'URL
'keys=chaufferies' -> 'keys=rbaconly_c4' dans le(s) fetch(...) du widget. La cle
'rbaconly_c4' n'existe pas cote TB -> l'endpoint renvoie [] -> le code existant
`var v = arr.filter(a=>a.key==='chaufferies')[0]; if (!v) return null;` resout la
promesse a null -> AUCUN filtre client -> le menu affiche ce que l'alias renvoie
(deja scope par le RBAC serveur). Le chemin `null` est exactement celui, eprouve,
des tenant-admins. On ne remplace qu'une chaine sans parentheses/accolades par une
autre : l'equilibrage du JS est PRESERVE (verifie par --self-test).

Historique : une 1re approche (remplacer toute l'expression fetch(...).catch(...)
par Promise.resolve(null)) a ete abandonnee — sur la vraie structure
`(function(){ ... return fetch()...; }).catch()`, le .catch est chaine a l'IIFE
englobante, et la regex mangeait le `})` de l'IIFE (balance -1,-1) -> JS casse.

Usage: TB_TOKEN=... python neutralize_chaufferies_filter.py <dashboardId> [--apply]
       python neutralize_chaufferies_filter.py --self-test
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rbac'))
import _lib_rbac as tb

NEEDLE = 'keys=chaufferies'      # cle d'URL du fetch de filtrage
REPL = 'keys=rbaconly_c4'        # cle inexistante -> [] -> filtre resout null. NE contient PAS 'chaufferies'.

def neutralize(text):
    """Retourne (nouveau_texte, nb_remplacements). Renomme la cle d'URL uniquement."""
    n = text.count(NEEDLE)
    return (text.replace(NEEDLE, REPL), n) if n else (text, 0)

def walk(obj, counter, spans=None):
    """Applique neutralize() sur toutes les chaines JSON du dashboard.
    Si spans est une liste, y accumule un extrait de contexte autour de chaque
    occurrence renommee (pour relecture en dry-run)."""
    if isinstance(obj, str):
        if spans is not None:
            i = obj.find(NEEDLE)
            while i != -1:
                spans.append(obj[max(0, i - 90):i + 60])
                i = obj.find(NEEDLE, i + 1)
        return neutralize(obj)[0] if _bump(obj, counter) else obj
    if isinstance(obj, list):
        return [walk(x, counter, spans) for x in obj]
    if isinstance(obj, dict):
        return {k: walk(v, counter, spans) for k, v in obj.items()}
    return obj

def _bump(text, counter):
    n = text.count(NEEDLE)
    counter[0] += n
    return n > 0

def _balance(t):
    """Delta (parentheses, accolades, crochets) — 0 partout = equilibre."""
    return (t.count('(') - t.count(')'),
            t.count('{') - t.count('}'),
            t.count('[') - t.count(']'))

# Fixture fidele a la structure REELLE du widget (IIFE englobante + .catch chaine
# a l'IIFE + `})();` final), et NON une chaine .then().catch() simplifiee.
SELFTEST_SAMPLE = (
    "SF.allowedP = (function(){\n"
    "      if (!u || !u.authority) return null;\n"
    "      if (u.authority === 'TENANT_ADMIN') return null;\n"
    "      var uid = u.id && u.id.id; if (!uid) return null;\n"
    "      return fetch('/api/plugins/telemetry/USER/'+uid+'/values/attributes/SERVER_SCOPE?keys=chaufferies', { headers: H() })\n"
    "        .then(function(rr){ return rr.ok ? rr.json() : []; })\n"
    "        .then(function(arr){\n"
    "          var v = (arr || []).filter(function(a){ return a.key === 'chaufferies'; })[0];\n"
    "          if (!v) return null; var list = v.value;\n"
    "          if (!Array.isArray(list) || !list.length) return null;\n"
    "          var s = new Set(); list.forEach(function(x){ s.add(String(x)); }); return s;\n"
    "        });\n"
    "    }).catch(function(){ return null; });\n"
    "})();\n")

def self_test():
    """Verifie neutralize() hors-ligne (aucun reseau). Leve AssertionError si KO."""
    out, n = neutralize(SELFTEST_SAMPLE)
    assert n == 1, f'attendu 1 renommage, obtenu {n}'
    assert 'keys=chaufferies' not in out, "'keys=chaufferies' encore present"
    assert 'keys=rbaconly_c4' in out, 'cle de remplacement absente'
    # LE point cle : la structure JS est intacte -> equilibrage PRESERVE.
    assert _balance(out) == _balance(SELFTEST_SAMPLE), (
        f'balance modifiee ! avant={_balance(SELFTEST_SAMPLE)} apres={_balance(out)} -> corruption')
    # Le chemin null existant est preserve (structure non touchee).
    for marker in ('if (!v) return null;', '.catch(function(){ return null; })', '})();'):
        assert marker in out, f'marqueur structurel disparu : {marker!r}'
    # Idempotence : 2e passe ne renomme rien de plus.
    _, n2 = neutralize(out)
    assert n2 == 0, f'non idempotent : {n2} renommage(s) en 2e passe'
    # fetch non lie (keys=other) -> jamais touche.
    _, n3 = neutralize("fetch('x?keys=other')")
    assert n3 == 0, 'ne doit pas toucher un fetch keys=other'
    print('SELF-TEST OK')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dashboard_id', nargs='?', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--self-test', action='store_true', help='teste neutralize() hors-ligne et quitte')
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
    cfg = d.get('configuration', {})
    before = json.dumps(cfg, ensure_ascii=False)
    bal_before = _balance(before)
    n_before = before.count(NEEDLE)
    counter = [0]
    spans = []
    d['configuration'] = walk(cfg, counter, spans)
    after = json.dumps(d.get('configuration', {}), ensure_ascii=False)
    n_after = after.count(NEEDLE)
    bal_after = _balance(after)

    print(f'dashboard {args.dashboard_id}')
    print(f'  occurrences "{NEEDLE}" AVANT={n_before}  APRES={n_after}  (renommees={counter[0]})')
    print(f'  balance JSON AVANT={bal_before}  APRES={bal_after}')
    if not args.apply and spans:
        for i, s in enumerate(spans, 1):
            print(f'--- contexte renomme {i}/{len(spans)} ---\n{s}')

    # Garde-fou balance : le renommage NE DOIT PAS changer l'equilibrage.
    if bal_after != bal_before:
        print('  ERREUR : balance modifiee par le renommage — ABANDON, rien ecrit.', file=sys.stderr)
        sys.exit(4)
    if n_before > 0 and counter[0] == 0:
        print(f'  ERREUR : "{NEEDLE}" present mais aucun renommage — ABANDON.', file=sys.stderr)
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

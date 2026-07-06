#!/usr/bin/env python3
"""Fix du bug de cablage du garde chantier 2 (rule chain "PAC Hybride Router").

Symptome : les devices provisionnes (site_assigned=true) ont leur cle `pac_v2`
figee + pas de `mark active` (badge hors-ligne) + pas d'alarmes DeviceProfile,
depuis la migration #2. Cause : la branche `Provisionnee ? --True-->` a ete
cablee vers le noeud de save d'evenements brut `save TS (per-id device)`, en
sautant tout le pipeline normal (Filter HPs present v2 -> TBEL -> Save TS pac_v2,
mark active, DeviceProfile).

Fix : rendre la branche True identique a la branche False MOINS l'assign, i.e.
recabler `Provisionnee ? --True-->` vers les 3 memes noeuds que
`Assign to Yahtec --Success-->` : {Filter HPs present v2, mark active,
DeviceProfile (alarms)} ; et retirer l'arete True -> save TS (per-id device).

Dry-run par defaut. Ecriture avec --apply. Token via TB_TOKEN (ou --user/--pwd).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rbac'))
import _lib_rbac as tb  # noqa: E402

RC_ID = 'b6af0570-4226-11f1-bbfe-e1395562cba0'  # PAC Hybride Router
SRC = 'Provisionnee ?'                # noeud filtre (source de la branche True)
WRONG_TARGET = 'save TS (per-id device)'  # cible actuelle (BUG) sur label "True"
GOOD_TARGETS = ['Filter HPs present v2', 'mark active', 'DeviceProfile (alarms)']
REF = 'Assign to Yahtec'              # ses cibles "Success" == GOOD_TARGETS (verif)
LABEL = 'True'


def idx_by_name(nodes, name):
    hits = [i for i, n in enumerate(nodes) if n.get('name') == name]
    if len(hits) != 1:
        sys.exit(f'ERREUR : noeud "{name}" trouve {len(hits)} fois (attendu 1).')
    return hits[0]


def conns_from(meta, src_i):
    return [(c['toIndex'], c['type']) for c in meta['connections'] if c['fromIndex'] == src_i]


def show(meta, label):
    nodes = meta['nodes']
    src_i = idx_by_name(nodes, SRC)
    print(f'  [{label}] connexions depuis "{SRC}" (idx {src_i}) :')
    for to_i, typ in sorted(conns_from(meta, src_i), key=lambda x: (x[1], x[0])):
        print(f'      --{typ}--> [{to_i}] {nodes[to_i]["name"]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='ecrit (defaut = dry-run)')
    ap.add_argument('--user', default=os.environ.get('TB_USER', 'je@yahtec.com'))
    ap.add_argument('--pwd', default=os.environ.get('TB_PWD'))
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    meta = tb.http_get(f'/api/ruleChain/{RC_ID}/metadata', t)
    nodes = meta['nodes']

    src_i = idx_by_name(nodes, SRC)
    wrong_i = idx_by_name(nodes, WRONG_TARGET)
    good_is = [idx_by_name(nodes, n) for n in GOOD_TARGETS]

    # Garde-fou : verifier que le noeud de reference (Assign to Yahtec) va bien
    # vers exactement GOOD_TARGETS en "Success" (sinon le modele a change).
    ref_i = idx_by_name(nodes, REF)
    ref_success = {to for to, typ in conns_from(meta, ref_i) if typ == 'Success'}
    if ref_success != set(good_is):
        got = sorted(nodes[i]['name'] for i in ref_success)
        sys.exit(f'ERREUR garde-fou : "{REF}" --Success--> {got} != {GOOD_TARGETS}. '
                 'Le rule chain a change ; revalider le fix a la main.')

    print(f'Rule chain {RC_ID}  ({len(nodes)} noeuds, {len(meta["connections"])} connexions)')
    show(meta, 'AVANT')

    # 1) retirer l'arete buggee : SRC --True--> WRONG_TARGET
    before = len(meta['connections'])
    meta['connections'] = [c for c in meta['connections']
                           if not (c['fromIndex'] == src_i and c['toIndex'] == wrong_i
                                   and c['type'] == LABEL)]
    removed = before - len(meta['connections'])

    # 2) ajouter SRC --True--> chacun des GOOD_TARGETS (si absent)
    existing = {(c['fromIndex'], c['toIndex'], c['type']) for c in meta['connections']}
    added = 0
    for to_i in good_is:
        key = (src_i, to_i, LABEL)
        if key not in existing:
            meta['connections'].append({'fromIndex': src_i, 'toIndex': to_i, 'type': LABEL})
            existing.add(key)
            added += 1

    print(f'\n  -> {removed} arete(s) retiree(s) (True -> {WRONG_TARGET}), '
          f'{added} ajoutee(s) (True -> {GOOD_TARGETS}).')
    show(meta, 'APRES (prevu)')

    if not args.apply:
        print('\nDRY-RUN : rien ecrit. Relancer avec --apply pour appliquer.')
        return

    tb.http_post('/api/ruleChain/metadata', meta, t)
    print('\nAPPLIQUE. Relecture de verification :')
    meta2 = tb.http_get(f'/api/ruleChain/{RC_ID}/metadata', t)
    show(meta2, 'RELU')


if __name__ == '__main__':
    main()

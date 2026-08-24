#!/usr/bin/env python3
"""Construction des patchs de source widget pour les registres capteurs gaz.

Logique pure : aucun appel reseau, entierement testable hors ligne. Les
enveloppes REST (patch-*.py) se contentent d'appeler ces fonctions.

Principe : la logique d'affichage vit dans _src/gas_lib.js, injectee telle
quelle en tete de chaque controllerScript. Les blocs conditionnels ecrits a la
main dans les widgets sont remplaces par un appel a cette lib.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAS_LIB_PATH = os.path.join(HERE, '_src', 'gas_lib.js')

# Presence de la lib dans la source = patch deja applique.
DONE_MARK = 'root.__gasLib = {'

# Cible -> (objet JS, suffixe de champ, prefixe de libelle d'origine)
TARGETS = {
    'HP':   {'obj': 'hp',   'sfx': 'R290'},
    'boil': {'obj': 'boil', 'sfx': 'G20'},
}


class AnchorError(RuntimeError):
    """Une ancre de remplacement est absente ou presente plusieurs fois."""


def load_gas_lib():
    """Contenu de _src/gas_lib.js, sans modification."""
    with open(GAS_LIB_PATH, encoding='utf-8') as f:
        return f.read()


def inject_lib(controller_script):
    """Prepend la lib au controllerScript. Sans effet si deja presente."""
    if DONE_MARK in controller_script:
        return controller_script
    return load_gas_lib().rstrip('\n') + '\n' + controller_script


def _old_block(obj, sfx):
    """Bloc conditionnel ecrit a la main dans la source live (sans saut de ligne)."""
    label = 'Concentration ' + sfx
    return (
        "({obj}.con{sfx}!=null?kv('{label}',{obj}.con{sfx}*0.1,' %LFL',1)"
        "+'<div class=\"pd-kv\"><span class=\"k\">Capteur {sfx}</span><span class=\"v\">'"
        "+({obj}.err{sfx}==null?'—':(Number({obj}.err{sfx})===0?'OK':String({obj}.err{sfx})))"
        "+'</span></div>':'')"
    ).format(obj=obj, sfx=sfx, label=label)


def table_replacements(target):
    """[(nom, ANCIEN, NOUVEAU)] pour un widget de table."""
    t = TARGETS[target]
    return [(
        f'lignes gaz {t["sfx"]}',
        _old_block(t['obj'], t['sfx']),
        f"window.__gasLib.rows('{t['sfx']}',{t['obj']})",
    )]


def patch_table(controller_script, target):
    """(nouvelle_source, notes). Idempotent."""
    if DONE_MARK in controller_script:
        return controller_script, ['lib deja injectee (skip)']
    notes = []
    out = controller_script
    for name, old, new in table_replacements(target):
        n = out.count(old)
        if n != 1:
            raise AnchorError(f'[{name}] ancre {n}x (attendu 1) -- source live a change')
        out = out.replace(old, new, 1)
        notes.append(f'[{name}] OK ({len(old)} -> {len(new)} c)')
    out = inject_lib(out)
    notes.append(f'lib injectee ({len(load_gas_lib())} c)')
    return out, notes

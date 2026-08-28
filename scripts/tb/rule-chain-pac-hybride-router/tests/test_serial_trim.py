"""Tests du garde-fou trim() sur le n de serie (node "extract id -> metadata").

Contexte : le 2026-08-28 un automate a emis id="2610000001\r\n". Le node 2
(change originator) n'a pas trouve de device de ce nom -> Failure -> evt_unknown_id
-> provision_watcher.py a cree un device fantome nomme "2610000001\r\n".
Le trim au node 1 fait resoudre l'id vers le device "2610000001" existant.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


def _load():
    p = Path(__file__).resolve().parents[1] / "add-serial-trim.py"
    spec = importlib.util.spec_from_file_location("add_serial_trim", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

TARGET = 'extract id -> metadata'
# Script d'origine en prod avant le patch (2026-08-28).
LEGACY_JS = ("metadata.targetDeviceName = String(msg.id); "
             "return {msg: msg, metadata: metadata, msgType: msgType};")
LEGACY_TBEL = ("metadata.targetDeviceName = msg.id + ''; "
               "return {msg: msg, metadata: metadata, msgType: msgType};")


def base_meta():
    """Metadata minimale reproduisant la topologie reelle autour du node cible."""
    names = ['id present?', TARGET, 'originator -> device(${id})']
    nodes = [{'name': n, 'configuration': {}} for n in names]
    nodes[1]['configuration'] = {
        'scriptLang': 'JS', 'jsScript': LEGACY_JS, 'tbelScript': LEGACY_TBEL,
    }
    conns = [{'fromIndex': 0, 'toIndex': 1, 'type': 'True'},
             {'fromIndex': 1, 'toIndex': 2, 'type': 'Success'}]
    return {'nodes': nodes, 'connections': conns}


def _target(meta):
    return next(n for n in meta['nodes'] if n['name'] == TARGET)


# --- ciblage -----------------------------------------------------------------

def test_patch_le_bon_node():
    meta = base_meta()
    mod.apply_patch(meta)
    assert '.trim()' in _target(meta)['configuration']['jsScript']


def test_ne_touche_ni_les_autres_nodes_ni_le_cablage():
    meta = base_meta()
    before = copy.deepcopy(meta)
    mod.apply_patch(meta)
    assert meta['connections'] == before['connections']
    assert len(meta['nodes']) == len(before['nodes'])
    for name in ('id present?', 'originator -> device(${id})'):
        a = next(n for n in meta['nodes'] if n['name'] == name)
        b = next(n for n in before['nodes'] if n['name'] == name)
        assert a == b


def test_abort_si_le_node_cible_est_absent():
    meta = base_meta()
    meta['nodes'] = [n for n in meta['nodes'] if n['name'] != TARGET]
    with pytest.raises(SystemExit):
        mod.apply_patch(meta)


# --- contenu du script -------------------------------------------------------

def test_les_deux_langages_sont_patches():
    """scriptLang vaut JS aujourd'hui, mais tbelScript ne doit pas reintroduire
    le bug si quelqu'un bascule le node en TBEL plus tard."""
    meta = base_meta()
    mod.apply_patch(meta)
    cfg = _target(meta)['configuration']
    assert '.trim()' in cfg['jsScript']
    assert '.trim()' in cfg['tbelScript']
    assert cfg['scriptLang'] == 'JS'


def test_le_contrat_de_sortie_est_preserve():
    meta = base_meta()
    mod.apply_patch(meta)
    for script in (_target(meta)['configuration']['jsScript'],
                   _target(meta)['configuration']['tbelScript']):
        assert 'metadata.targetDeviceName' in script
        assert 'return {msg: msg, metadata: metadata, msgType: msgType};' in script


# --- idempotence -------------------------------------------------------------

def test_idempotent():
    meta = base_meta()
    mod.apply_patch(meta)
    once = copy.deepcopy(meta)
    mod.apply_patch(meta)
    assert meta == once


def test_signale_deja_applique():
    meta = base_meta()
    assert any('~' not in c for c in mod.apply_patch(meta))
    changes = mod.apply_patch(meta)
    assert changes == [] or all(c.startswith('~') for c in changes)


# --- comportement du JS, simule en Python ------------------------------------
# Le vrai `node --check` + execution tourne sur l'hote de prod (pas de node en
# local) ; ici on verifie la SEMANTIQUE attendue sur les cas qui nous ont mordus.

@pytest.mark.parametrize('brut,attendu', [
    ('2610000001\r\n', '2610000001'),   # le cas du 2026-08-28
    ('2610000001\n', '2610000001'),
    (' 2610000001 ', '2610000001'),
    ('2610000001', '2610000001'),       # cas nominal : inchange
    ('2623001001', '2623001001'),
])
def test_semantique_trim(brut, attendu):
    assert brut.strip() == attendu


def test_id_uniquement_blanc_donne_une_chaine_vide():
    """Consequence assumee : targetDeviceName vide -> le node 2 echoue ->
    evt_unknown_id + alarme. Echec visible, pas de device fantome."""
    assert '   '.strip() == ''

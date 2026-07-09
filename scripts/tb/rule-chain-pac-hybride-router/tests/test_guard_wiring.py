import importlib.util
from pathlib import Path
import pytest


def _load():
    p = Path(__file__).resolve().parents[1] / "guard-assign-node.py"
    spec = importlib.util.spec_from_file_location("guard_assign_node", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
ORIG = 'originator -> device(${id})'
SAVE = 'save TS (per-id device)'
ASSIGN = 'Assign to Yahtec'


def base_meta():
    names = [ORIG, SAVE, ASSIGN, *mod.GOOD_TARGETS]
    nodes = [{'name': n} for n in names]
    i = {n: k for k, n in enumerate(names)}
    conns = [{'fromIndex': i[ORIG], 'toIndex': i[ASSIGN], 'type': 'Success'}]
    conns += [{'fromIndex': i[ASSIGN], 'toIndex': i[g], 'type': 'Success'} for g in mod.GOOD_TARGETS]
    return {'nodes': nodes, 'connections': conns}


def _edges(meta, frm_name, typ):
    names = [n['name'] for n in meta['nodes']]
    frm = names.index(frm_name)
    return sorted(meta['nodes'][c['toIndex']]['name'] for c in meta['connections']
                  if c['fromIndex'] == frm and c['type'] == typ)


def test_true_branch_goes_to_good_targets_not_save():
    meta = base_meta()
    info = mod.apply_guard(meta)
    assert info['status'] == 'applied'
    assert _edges(meta, 'Provisionnee ?', 'True') == sorted(mod.GOOD_TARGETS)
    assert SAVE not in _edges(meta, 'Provisionnee ?', 'True')
    assert _edges(meta, 'Provisionnee ?', 'False') == [ASSIGN]
    assert _edges(meta, ORIG, 'Success') == ['load site_assigned']


def test_guardrail_aborts_when_ref_changed():
    meta = base_meta()
    names = [n['name'] for n in meta['nodes']]
    assign = names.index(ASSIGN)
    meta['connections'] = [c for c in meta['connections'] if c['fromIndex'] != assign]
    meta['connections'].append({'fromIndex': assign, 'toIndex': names.index(SAVE), 'type': 'Success'})
    with pytest.raises(SystemExit):
        mod.apply_guard(meta)


def test_idempotent_when_guard_active():
    meta = base_meta()
    mod.apply_guard(meta)
    assert mod.apply_guard(meta)['status'] == 'active'


def corrupted_meta_with_guard_present():
    """Garde deja cablee (getattr+filter presents, ORIG->getattr->filter OK) mais
    la branche True du filtre pointe vers SAVE au lieu de GOOD_TARGETS
    (= le bug historique fix-guard-true-branch.py etait censee corriger)."""
    names = [ORIG, SAVE, ASSIGN, mod.GETATTR, mod.FILTER, *mod.GOOD_TARGETS]
    nodes = [{'name': n} for n in names]
    i = {n: k for k, n in enumerate(names)}
    conns = [
        {'fromIndex': i[ASSIGN], 'toIndex': i[g], 'type': 'Success'} for g in mod.GOOD_TARGETS
    ] + [
        {'fromIndex': i[ORIG], 'toIndex': i[mod.GETATTR], 'type': 'Success'},
        {'fromIndex': i[mod.GETATTR], 'toIndex': i[mod.FILTER], 'type': 'Success'},
        {'fromIndex': i[mod.GETATTR], 'toIndex': i[mod.FILTER], 'type': 'Failure'},
        {'fromIndex': i[mod.FILTER], 'toIndex': i[ASSIGN], 'type': 'False'},
        {'fromIndex': i[mod.FILTER], 'toIndex': i[SAVE], 'type': 'True'},
    ]
    return {'nodes': nodes, 'connections': conns}


def test_repairs_corrupted_true_branch_when_guard_already_present():
    meta = corrupted_meta_with_guard_present()
    info = mod.apply_guard(meta)
    assert info['status'] == 'applied'
    assert info['reused'] is True
    assert _edges(meta, mod.FILTER, 'True') == sorted(mod.GOOD_TARGETS)
    assert SAVE not in _edges(meta, mod.FILTER, 'True')


def test_guard_status_active_on_conforme():
    meta = base_meta()
    mod.apply_guard(meta)  # rend conforme
    assert mod.guard_status(meta) == 'active'
    # guard_status ne doit PAS muter l'argument
    before = [dict(c) for c in meta['connections']]
    mod.guard_status(meta)
    assert meta['connections'] == before


def test_guard_status_applied_on_corrupted():
    assert mod.guard_status(base_meta()) == 'applied'

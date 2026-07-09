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

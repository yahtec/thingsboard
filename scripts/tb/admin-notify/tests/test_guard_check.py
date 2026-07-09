import guard_check as g


def meta_ok():
    names = [g.ORIG, g.GETATTR, g.FILTER, g.ASSIGN, *g.GOOD_TARGETS]
    i = {n: k for k, n in enumerate(names)}
    conns = [
        {'fromIndex': i[g.ORIG], 'toIndex': i[g.GETATTR], 'type': 'Success'},
        {'fromIndex': i[g.GETATTR], 'toIndex': i[g.FILTER], 'type': 'Success'},
        {'fromIndex': i[g.GETATTR], 'toIndex': i[g.FILTER], 'type': 'Failure'},
        {'fromIndex': i[g.FILTER], 'toIndex': i[g.ASSIGN], 'type': 'False'},
    ] + [{'fromIndex': i[g.FILTER], 'toIndex': i[t], 'type': 'True'} for t in g.GOOD_TARGETS]
    return {'nodes': [{'name': n} for n in names], 'connections': conns}


def _drop(meta, pred):
    meta = {'nodes': meta['nodes'], 'connections': [c for c in meta['connections'] if not pred(c)]}
    return meta


def test_ok():
    ok, problems = g.check_guard(meta_ok())
    assert ok and problems == []


def test_bypass_direct_orig_to_assign():
    m = meta_ok()
    names = [n['name'] for n in m['nodes']]
    # supprime orig->getattr, ajoute orig->assign (garde contournée)
    oi, gi, ai = names.index(g.ORIG), names.index(g.GETATTR), names.index(g.ASSIGN)
    m = _drop(m, lambda c: c['fromIndex'] == oi and c['toIndex'] == gi)
    m['connections'].append({'fromIndex': oi, 'toIndex': ai, 'type': 'Success'})
    ok, problems = g.check_guard(m)
    assert not ok and any('BYPASS' in p for p in problems)


def test_true_branch_to_save():
    m = meta_ok()
    names = [n['name'] for n in m['nodes']]
    fi = names.index(g.FILTER)
    m = _drop(m, lambda c: c['fromIndex'] == fi and c['type'] == 'True')
    # ajoute un node 'save TS (per-id device)' et branche True dessus
    m['nodes'].append({'name': 'save TS (per-id device)'})
    m['connections'].append({'fromIndex': fi, 'toIndex': len(m['nodes']) - 1, 'type': 'True'})
    ok, problems = g.check_guard(m)
    assert not ok and any('True' in p for p in problems)


def test_guard_absent():
    ok, problems = g.check_guard({'nodes': [{'name': g.ORIG}, {'name': g.ASSIGN}], 'connections': []})
    assert not ok and problems


def test_getattr_to_filter_severed():
    m = meta_ok()
    names = [n['name'] for n in m['nodes']]
    gi, fi = names.index(g.GETATTR), names.index(g.FILTER)
    m = _drop(m, lambda c: c['fromIndex'] == gi and c['toIndex'] == fi and c['type'] == 'Success')
    ok, problems = g.check_guard(m)
    assert not ok and any('routage' in p or (g.GETATTR in p and g.FILTER in p) for p in problems)


def test_decide_alert():
    assert g.decide_alert('OK', 'OK') == (False, None)
    assert g.decide_alert('OK', 'DRIFT') == (True, 'lost')
    assert g.decide_alert('DRIFT', 'OK') == (True, 'recovered')
    assert g.decide_alert('DRIFT', 'DRIFT') == (False, None)
    assert g.decide_alert(None, 'OK') == (False, None)
    assert g.decide_alert(None, 'DRIFT') == (True, 'lost')


def test_should_persist():
    assert g.should_persist(False, False) is True
    assert g.should_persist(False, True) is True
    assert g.should_persist(True, True) is True
    assert g.should_persist(True, False) is False

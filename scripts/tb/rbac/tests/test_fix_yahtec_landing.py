"""I19 : fix_yahtec_landing.py:49 fait un fetch monopage /api/users (pageSize=1000) sans
verifier hasNext. Au-dela de 1000 users, le script traiterait silencieusement un
sous-ensemble et laisserait des comptes sans landing yahtec sans jamais le signaler.
Fix : si hasNext -> sys.exit avant tout traitement."""
import sys
from pathlib import Path

import pytest

RBAC_DIR = Path(__file__).resolve().parents[1]


def _load():
    import importlib.util
    if str(RBAC_DIR) not in sys.path:
        sys.path.insert(0, str(RBAC_DIR))
    p = RBAC_DIR / "fix_yahtec_landing.py"
    spec = importlib.util.spec_from_file_location("fix_yahtec_landing", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
tb = mod.tb

USERS_PATH_PREFIX = '/api/users?pageSize=1000&page=0'


def test_users_page_overflow_hard_exits_before_any_write(monkeypatch, capsys):
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['fix_yahtec_landing.py'])  # dry-run

    page = {'data': [{'email': 'a@test.com', 'authority': 'CUSTOMER_USER',
                       'additionalInfo': {}}], 'hasNext': True}
    monkeypatch.setattr(tb, 'http_get', lambda p, t, allow_404=False, allow_400=False: page)

    def boom(*a, **k):
        raise AssertionError('aucun traitement/ecriture attendu sur une page tronquee')

    monkeypatch.setattr(tb, 'http_post', boom)

    with pytest.raises(SystemExit):
        mod.main()

    out = capsys.readouterr().out
    assert 'a@test.com' not in out  # pas de traitement partiel silencieux


def test_users_single_page_no_overflow_runs_normally(monkeypatch, capsys):
    """Non-regression : hasNext absent/False -> comportement inchange (dry-run)."""
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['fix_yahtec_landing.py'])

    page = {'data': [{'email': 'a@test.com', 'authority': 'CUSTOMER_USER',
                       'additionalInfo': {}}], 'hasNext': False}
    monkeypatch.setattr(tb, 'http_get', lambda p, t, allow_404=False, allow_400=False: page)

    mod.main()  # ne doit pas lever SystemExit

    out = capsys.readouterr().out
    assert 'a@test.com' in out

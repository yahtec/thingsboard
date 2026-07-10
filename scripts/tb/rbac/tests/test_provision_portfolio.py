"""I18 : ensure_user peut renvoyer CUSTOMER_MISMATCH (email deja utilise sous un autre
customer, customerId immuable cote TB) — provision_portfolio.main() doit le consommer,
le signaler bruyamment et sortir non-zero, SANS masquer le rapport '== Termine =='."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

RBAC_DIR = Path(__file__).resolve().parents[1]


def _load():
    if str(RBAC_DIR) not in sys.path:
        sys.path.insert(0, str(RBAC_DIR))
    p = RBAC_DIR / "provision_portfolio.py"
    spec = importlib.util.spec_from_file_location("provision_portfolio", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
tb = mod.tb


def _write_cfg(tmp_path, cfg):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding='utf-8')
    return p


def test_main_reports_customer_mismatch_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    cfg = {
        "sites": [],
        "parties": [{"title": "Party X", "role": "PARTY", "userEmail": "dup@test.com",
                     "canView": []}],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-partyx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: tb.CUSTOMER_MISMATCH)
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out  # le rapport final n'est pas masque par l'exit non-zero
    assert 'dup@test.com' in out
    assert exc.value.code != 0


def test_main_reports_customer_mismatch_for_staff_too(tmp_path, monkeypatch, capsys):
    cfg = {
        "sites": [],
        "parties": [],
        "staff": [{"title": "Staff X", "role": "STAFF", "userEmail": "dupstaff@test.com",
                   "excluded": []}],
    }
    cfg_path = _write_cfg(tmp_path, cfg)

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-staffx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: tb.CUSTOMER_MISMATCH)
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out
    assert 'dupstaff@test.com' in out
    assert exc.value.code != 0


def test_main_normal_run_no_mismatch_does_not_exit_nonzero(tmp_path, monkeypatch, capsys):
    """Non-regression : un run normal (aucun mismatch) ne doit pas lever SystemExit."""
    cfg = {
        "sites": [],
        "parties": [{"title": "Party OK", "role": "PARTY", "userEmail": "ok@test.com",
                     "canView": []}],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-1')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    mod.main()  # ne doit pas lever SystemExit

    out = capsys.readouterr().out
    assert 'Termine' in out

import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    p = Path(__file__).resolve().parents[1] / "create_service_account.py"
    spec = importlib.util.spec_from_file_location("create_service_account", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
tb = mod.tb


def test_gen_password_strong_and_random():
    p1, p2 = mod.gen_password(), mod.gen_password()
    assert len(p1) >= 24
    assert p1 != p2  # aléatoire


def test_build_body_tenant_admin_headless():
    b = mod.build_body("svc-tbnotify@yahtec.com")
    assert b["email"] == "svc-tbnotify@yahtec.com"
    assert b["authority"] == "TENANT_ADMIN"
    assert "customerId" not in b            # headless, aucun customer
    assert b["additionalInfo"]["description"]  # documenté


# ---------- I15 : compte existant mais jamais active (POST ok, activation avait echoue) ----------

def _existing(uid='uid-1', email=None):
    return {'id': {'id': uid}, 'email': email or mod.DEFAULT_EMAIL}


def test_main_existing_and_already_activated_is_true_noop(monkeypatch, capsys):
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['create_service_account.py'])
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: _existing())
    monkeypatch.setattr(tb, 'get_activation_link_info', lambda t, uid: None)

    def boom(*a, **k):
        raise AssertionError('aucune ecriture attendue : deja actif')

    monkeypatch.setattr(tb, 'http_post', boom)

    mod.main()

    out = capsys.readouterr().out
    assert 'actif' in out.lower()


def test_main_existing_but_not_activated_dry_run_no_write(monkeypatch, capsys):
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['create_service_account.py'])  # dry-run par defaut
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: _existing())
    monkeypatch.setattr(tb, 'get_activation_link_info',
                         lambda t, uid: {'value': 'http://tb/x?activateToken=tok-1'})

    def boom(*a, **k):
        raise AssertionError('dry-run ne doit rien ecrire')

    monkeypatch.setattr(tb, 'http_post', boom)

    mod.main()

    out = capsys.readouterr().out
    assert 'PAS' in out.upper() and 'ACTIV' in out.upper()
    assert 'DRY' in out.upper()


def test_main_existing_but_not_activated_apply_reactivates(monkeypatch, capsys):
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['create_service_account.py', '--apply', '--new-pwd', 'MyP@ss1234'])
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: _existing())
    monkeypatch.setattr(tb, 'get_activation_link_info',
                         lambda t, uid: {'value': 'http://tb/x?activateToken=abc-123'})
    posts = []
    monkeypatch.setattr(tb, 'http_post', lambda p, b, t: posts.append((p, b)) or {})

    mod.main()

    out = capsys.readouterr().out
    assert posts == [('/api/noauth/activate', {'activateToken': 'abc-123', 'password': 'MyP@ss1234'})]
    assert 'MyP@ss1234' in out


def test_main_existing_but_not_activated_apply_no_token_hard_fails(monkeypatch):
    """Non-regression : un lien d'activation sans token (etat serveur inattendu) doit
    rester une erreur dure, comme au chemin creation."""
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['create_service_account.py', '--apply'])
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: _existing())
    monkeypatch.setattr(tb, 'get_activation_link_info',
                         lambda t, uid: {'value': 'http://tb/x?nope=1'})

    def boom(*a, **k):
        raise AssertionError('pas de POST attendu sans token')

    monkeypatch.setattr(tb, 'http_post', boom)

    with pytest.raises(SystemExit):
        mod.main()

"""I13 : un legacy droit_acces=admin ne doit plus etre recree en CUSTOMER_USER+ADMIN_OPS
(hybride invalide). Hard-fail AVANT toute mutation, skip, exit non-zero en listant les
comptes admin restes en LEGACY (a migrer a la main en TENANT_ADMIN, comme ac@)."""
import importlib.util
import sys
from pathlib import Path

import pytest

RBAC_DIR = Path(__file__).resolve().parents[1]


def _load():
    # migrate_legacy_to_rbac.py fait `import _lib_rbac as tb` sans se rajouter lui-meme
    # au sys.path (contrairement a create_service_account.py) : on le fait ici.
    if str(RBAC_DIR) not in sys.path:
        sys.path.insert(0, str(RBAC_DIR))
    p = RBAC_DIR / "migrate_legacy_to_rbac.py"
    spec = importlib.util.spec_from_file_location("migrate_legacy_to_rbac", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
tb = mod.tb


def make_user(email='admin@yahtec.com', uid='uid-admin'):
    return {'id': {'id': uid}, 'email': email, 'authority': 'CUSTOMER_USER',
            'firstName': None, 'lastName': None, 'additionalInfo': {}}


class Calls:
    """Compte les appels de mutation pour verifier qu'aucun n'a lieu sur un droit=admin."""
    def __init__(self):
        self.ensure_customer = []
        self.ensure_relation = []
        self.http_delete = []
        self.http_post = []
        self.save_server_attrs = []
        self.assign_dashboard_to_customer = []


@pytest.fixture
def patched(monkeypatch):
    calls = Calls()

    def fake_get_server_attrs(t, entity_type, entity_id, keys=None):
        # attrs du user admin : chaufferies non vide + droit_acces=admin
        return {'chaufferies': ['dev-1'], 'droit_acces': 'admin'}

    def fake_ensure_customer(t, title, apply):
        calls.ensure_customer.append(title)
        return 'party-cid-should-not-be-created'

    def fake_ensure_relation(t, from_cid, to_cid, rel_type, apply):
        calls.ensure_relation.append((from_cid, to_cid, rel_type))

    def fake_http_delete(p, t):
        calls.http_delete.append(p)

    def fake_http_post(p, body, t):
        calls.http_post.append((p, body))
        return {'id': {'id': 'new-uid'}}

    def fake_save_server_attrs(t, entity_type, entity_id, attrs, apply):
        calls.save_server_attrs.append((entity_type, entity_id, attrs))

    def fake_assign_dashboard(t, cid, dash, apply):
        calls.assign_dashboard_to_customer.append((cid, dash))

    monkeypatch.setattr(tb, 'get_server_attrs', fake_get_server_attrs)
    monkeypatch.setattr(tb, 'ensure_customer', fake_ensure_customer)
    monkeypatch.setattr(tb, 'ensure_relation', fake_ensure_relation)
    monkeypatch.setattr(tb, 'http_delete', fake_http_delete)
    monkeypatch.setattr(tb, 'http_post', fake_http_post)
    monkeypatch.setattr(tb, 'save_server_attrs', fake_save_server_attrs)
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', fake_assign_dashboard)
    return calls


def test_admin_user_dry_run_no_mutation_and_message(patched, capsys):
    u = make_user()
    result = mod._migrate_user(t=object(), u=u, apply=False)
    out = capsys.readouterr().out
    assert 'TENANT_ADMIN' in out
    assert 'ac@' in out
    assert not patched.ensure_customer
    assert not patched.ensure_relation
    assert not patched.http_delete
    assert not patched.http_post
    # Le hard-fail doit remonter un signal exploitable par main() pour l'exit non-zero.
    assert result == u['email']


def test_admin_user_apply_no_delete_no_create(patched, capsys):
    u = make_user()
    result = mod._migrate_user(t=object(), u=u, apply=True)
    assert not patched.ensure_customer
    assert not patched.ensure_relation
    assert not patched.http_delete
    assert not patched.http_post
    assert not patched.save_server_attrs
    assert result == u['email']


def test_non_admin_user_still_migrates_normally(monkeypatch, capsys):
    """Non-regression : un droit=lecture avec chaufferies doit toujours suivre le chemin normal."""
    def fake_get_server_attrs(t, entity_type, entity_id, keys=None):
        return {'chaufferies': ['dev-1'], 'droit_acces': 'lecture'}

    calls = []
    monkeypatch.setattr(tb, 'get_server_attrs', fake_get_server_attrs)
    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: calls.append(title) or None)
    monkeypatch.setattr(tb, 'ensure_relation', lambda *a, **k: calls.append('relation'))

    u = make_user(email='party@test.com', uid='uid-party')
    result = mod._migrate_user(t=object(), u=u, apply=False)
    assert result is None
    assert calls  # le chemin normal a bien tourne (ensure_customer appele)


def test_main_skips_admin_reports_and_exits_nonzero(monkeypatch, capsys):
    """Bout-en-bout main() : un admin + un normal dans la liste -> l'admin est skippe
    (pas de customer/relation cree pour lui), le normal continue de suivre le chemin
    normal, le run liste l'admin skippe et sort non-zero SANS faire disparaitre le
    rapport '== Termine =='."""
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['migrate_legacy_to_rbac.py'])  # dry-run par defaut

    admin_user = make_user(email='admin@yahtec.com', uid='uid-admin')
    normal_user = make_user(email='party@test.com', uid='uid-party')

    monkeypatch.setattr(tb, 'list_devices_by_profile', lambda t, profile: [])
    monkeypatch.setattr(mod, '_users_under', lambda t, cid: [admin_user, normal_user])
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: None)  # sections C/D no-op

    def fake_get_server_attrs(t, entity_type, entity_id, keys=None):
        if entity_type == 'USER' and entity_id == 'uid-admin':
            return {'chaufferies': ['dev-1'], 'droit_acces': 'admin'}
        if entity_type == 'USER':
            return {'chaufferies': ['dev-1'], 'droit_acces': 'lecture'}
        return {}  # lookup DEVICE site_customer_id -> absent, non-bloquant pour ce test

    ensure_customer_calls = []
    monkeypatch.setattr(tb, 'get_server_attrs', fake_get_server_attrs)
    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: ensure_customer_calls.append(title) or None)
    monkeypatch.setattr(tb, 'ensure_relation', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out  # le rapport n'est pas masque par l'exit non-zero
    assert 'admin@yahtec.com' in out
    assert exc.value.code != 0
    # seul le user normal declenche la creation de son party-customer ; l'admin est
    # skippe AVANT tout appel de mutation (ensure_customer/ensure_relation).
    assert ensure_customer_calls == ['Party — party@test.com']

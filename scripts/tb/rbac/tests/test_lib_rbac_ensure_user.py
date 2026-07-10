"""Tests directs de _lib_rbac.py : ensure_user (I15 reactivation, I18 mismatch,
KIOSK-on-update, email case-insensitive) + les helpers http bas niveau (http_get_text,
get_activation_link_info). conftest.py insere le repertoire parent dans sys.path."""
import io
import json
import urllib.error
import urllib.request

import pytest

import _lib_rbac as tb


# ---------- http_get_text (gestion d'erreur alignee sur les autres helpers) ----------

def test_http_get_text_ok_returns_raw_text(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'http://tb/api/noauth/activate?activateToken=abc'

    monkeypatch.setattr(urllib.request, 'urlopen', lambda req, timeout=None: FakeResp())
    assert tb.http_get_text('/api/user/u1/activationLink', 'tok') == \
        'http://tb/api/noauth/activate?activateToken=abc'


def test_http_get_text_exits_readably_on_http_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, 'Server Error', {}, io.BytesIO(b'boom'))

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    with pytest.raises(SystemExit) as exc:
        tb.http_get_text('/api/user/u1/activationLink', 'tok')
    assert 'HTTP 500' in str(exc.value)


# ---------- get_activation_link_info (I15 : detection du statut d'activation) ----------

class FakeJsonResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def test_get_activation_link_info_returns_value_when_pending(monkeypatch):
    monkeypatch.setattr(
        urllib.request, 'urlopen',
        lambda req, timeout=None: FakeJsonResp({'value': 'http://tb/x?activateToken=tok-1', 'ttlMs': 1}))
    info = tb.get_activation_link_info('tok', 'uid-1')
    assert info['value'] == 'http://tb/x?activateToken=tok-1'


def test_get_activation_link_info_none_when_already_activated(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, 'Bad Request', {},
                                      io.BytesIO(b'{"message":"User is already activated!"}'))

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    assert tb.get_activation_link_info('tok', 'uid-1') is None


def test_get_activation_link_info_exits_on_other_http_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, 'Server Error', {}, io.BytesIO(b'boom'))

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    with pytest.raises(SystemExit):
        tb.get_activation_link_info('tok', 'uid-1')


# ---------- find_user_by_email (M : comparaison insensible a la casse) ----------

def test_find_user_by_email_case_insensitive(monkeypatch):
    page = {'data': [{'id': {'id': 'u1'}, 'email': 'Julien@Yahtec.com'}]}
    monkeypatch.setattr(tb, 'http_get', lambda p, t, allow_404=False: page)
    u = tb.find_user_by_email('tok', 'julien@yahtec.com')
    assert u is not None and u['id']['id'] == 'u1'


def test_find_user_by_email_no_match_returns_none(monkeypatch):
    page = {'data': [{'id': {'id': 'u1'}, 'email': 'other@yahtec.com'}]}
    monkeypatch.setattr(tb, 'http_get', lambda p, t, allow_404=False: page)
    assert tb.find_user_by_email('tok', 'julien@yahtec.com') is None


# ---------- ensure_user : I15 (compte cree-mais-jamais-active irreparable) ----------

def _user(role, customer_id='cust-1', email='party@test.com', uid='uid-1', extra_info=None):
    ai = {'portfolioRole': role}
    if extra_info:
        ai.update(extra_info)
    return {'id': {'id': uid}, 'email': email,
            'customerId': {'id': customer_id} if customer_id else None,
            'additionalInfo': ai}


def test_ensure_user_role_ok_but_not_activated_reactivates_on_apply(monkeypatch):
    u = _user('PARTY')
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info',
                         lambda t, uid: {'value': 'http://tb/x?activateToken=tok-123'})
    posts = []
    monkeypatch.setattr(tb, 'http_post', lambda p, b, t: posts.append((p, b)) or {})

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-1', 'PARTY',
                             'newpwd', True)

    assert result == 'uid-1'
    assert ('/api/noauth/activate', {'activateToken': 'tok-123', 'password': 'newpwd'}) in posts


def test_ensure_user_role_ok_and_already_activated_is_a_true_noop(monkeypatch):
    u = _user('PARTY')
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info', lambda t, uid: None)

    def boom(*a, **k):
        raise AssertionError('aucune ecriture attendue : deja active')

    monkeypatch.setattr(tb, 'http_post', boom)

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-1', 'PARTY',
                             'newpwd', True)
    assert result == 'uid-1'


def test_ensure_user_not_activated_dry_run_reads_but_writes_nothing(monkeypatch, capsys):
    u = _user('PARTY')
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info',
                         lambda t, uid: {'value': 'http://tb/x?activateToken=tok-1'})

    def boom(*a, **k):
        raise AssertionError('dry-run ne doit rien ecrire')

    monkeypatch.setattr(tb, 'http_post', boom)

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-1', 'PARTY',
                             'newpwd', False)
    out = capsys.readouterr().out
    assert result == 'uid-1'
    assert 'DRY' in out


def test_ensure_user_no_password_does_not_probe_activation(monkeypatch):
    """Sans mot de passe fourni, pas d'intention d'activation -> ne pas interroger le
    statut (comportement de creation-sans-mdp preserve)."""
    u = _user('PARTY')
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)

    def boom(*a, **k):
        raise AssertionError('ne doit pas verifier l\'activation sans mot de passe')

    monkeypatch.setattr(tb, 'get_activation_link_info', boom)

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-1', 'PARTY',
                             None, True)
    assert result == 'uid-1'


# ---------- ensure_user : I18 (customerId existant != demande) ----------

def test_ensure_user_customer_mismatch_is_detected_and_reported(monkeypatch, capsys):
    u = _user('PARTY', customer_id='cust-OTHER')
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)

    def boom(*a, **k):
        raise AssertionError('aucune ecriture / lecture supplementaire sur mismatch')

    monkeypatch.setattr(tb, 'http_post', boom)
    monkeypatch.setattr(tb, 'get_activation_link_info', boom)

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-EXPECTED', 'PARTY',
                             None, True)

    out = capsys.readouterr().out
    assert result == tb.CUSTOMER_MISMATCH
    assert '!!' in out
    assert 'cust-OTHER' in out or 'cust-EXPECTED' in out


def test_ensure_user_no_mismatch_when_customer_id_not_requested(monkeypatch):
    """authority TENANT_ADMIN : customer_id demande = None -> pas de comparaison (le
    customerId existant, quel qu'il soit, n'est pas pertinent)."""
    u = _user('ADMIN_OPS', customer_id=None)
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info', lambda t, uid: None)

    result = tb.ensure_user('tok', 'party@test.com', 'TENANT_ADMIN', None, 'ADMIN_OPS', None, True)
    assert result == 'uid-1'


# ---------- ensure_user : KIOSK applique aussi sur le chemin UPDATE ----------

def test_ensure_user_update_to_party_applies_kiosk_fields(monkeypatch):
    u = _user('STAFF')  # role actuel STAFF, pas de champs kiosk -> MAJ vers PARTY attendue
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info', lambda t, uid: None)
    posts = []
    monkeypatch.setattr(tb, 'http_post', lambda p, b, t: posts.append((p, b)) or {})

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-1', 'PARTY',
                             None, True)

    assert result == 'uid-1'
    assert len(posts) == 1
    path, body = posts[0]
    assert path == '/api/user'
    ai = body['additionalInfo']
    assert ai['portfolioRole'] == 'PARTY'
    assert ai['homeDashboardId'] == tb.KIOSK_DASH
    assert ai['defaultDashboardId'] == tb.KIOSK_DASH
    assert ai['defaultDashboardFullscreen'] is False
    assert ai['homeDashboardHideToolbar'] is True


def test_ensure_user_update_to_admin_ops_does_not_apply_kiosk(monkeypatch):
    u = _user('PARTY', customer_id=None)
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info', lambda t, uid: None)
    posts = []
    monkeypatch.setattr(tb, 'http_post', lambda p, b, t: posts.append((p, b)) or {})

    tb.ensure_user('tok', 'x@test.com', 'TENANT_ADMIN', None, 'ADMIN_OPS', None, True)

    ai = posts[0][1]['additionalInfo']
    assert ai['portfolioRole'] == 'ADMIN_OPS'
    assert 'homeDashboardId' not in ai


def test_ensure_user_update_dry_run_still_prints_pending_role_change(monkeypatch, capsys):
    u = _user('STAFF')
    monkeypatch.setattr(tb, 'find_user_by_email', lambda t, email: u)
    monkeypatch.setattr(tb, 'get_activation_link_info', lambda t, uid: None)

    def boom(*a, **k):
        raise AssertionError('dry-run ne doit rien ecrire')

    monkeypatch.setattr(tb, 'http_post', boom)

    result = tb.ensure_user('tok', 'party@test.com', 'CUSTOMER_USER', 'cust-1', 'PARTY',
                             None, False)
    out = capsys.readouterr().out
    assert result == 'uid-1'
    assert 'DRY' in out

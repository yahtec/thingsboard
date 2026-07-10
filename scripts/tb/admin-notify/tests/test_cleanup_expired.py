import logging

import cleanup_expired as ce
import common

NOW = 1_700_000_000_000  # ms epoch fixe pour les tests
PAST = NOW - 3600_000
FUTURE = NOW + 3600_000


def make_client(attrs_by_uid):
    """TBClient réel avec get_server_attrs mocké + espions sur les 2 appels
    d'effet de bord (set_credentials_enabled / save_server_attrs)."""
    c = common.TBClient(url="http://test", user="svc", password="x")
    c.get_server_attrs = lambda etype, eid, keys=None: dict(attrs_by_uid.get(eid, {}))
    c.calls = {"set_credentials_enabled": [], "save_server_attrs": []}

    def _set_cred(uid, enabled):
        c.calls["set_credentials_enabled"].append((uid, enabled))

    def _save_attrs(etype, eid, kv):
        c.calls["save_server_attrs"].append((etype, eid, dict(kv)))

    c.set_credentials_enabled = _set_cred
    c.save_server_attrs = _save_attrs
    return c


def user(uid, authority="CUSTOMER_USER", email="u@example.com"):
    return {"id": {"id": uid}, "email": email, "authority": authority}


def no_calls(c):
    return c.calls["set_credentials_enabled"] == [] and c.calls["save_server_attrs"] == []


def test_expired_customer_user_disabled():
    c = make_client({"u1": {"expiration_ts": PAST}})
    log = logging.getLogger("test_cleanup_expired")
    result = ce.process_user(c, user("u1"), NOW, log)
    assert result is True
    assert c.calls["set_credentials_enabled"] == [("u1", False)]
    assert c.calls["save_server_attrs"] == [("USER", "u1", {"deactivated": True})]


def test_tenant_admin_never_touched(caplog):
    c = make_client({"admin1": {"expiration_ts": PAST}})
    log = logging.getLogger("test_cleanup_expired")
    with caplog.at_level(logging.WARNING, logger="test_cleanup_expired"):
        result = ce.process_user(c, user("admin1", authority="TENANT_ADMIN"), NOW, log)
    assert result is False
    assert no_calls(c)
    assert any("admin1" in r.message for r in caplog.records)


def test_already_processed_is_idempotent():
    # Etat réel déjà convergé (credentials off côté TB modélisé par
    # l'attribut deactivated déjà True) : aucun ré-appel.
    c = make_client({"u1": {"expiration_ts": PAST, "deactivated": True}})
    log = logging.getLogger("test_cleanup_expired")
    result = ce.process_user(c, user("u1"), NOW, log)
    assert result is False
    assert no_calls(c)


def test_non_expired_user_untouched():
    c = make_client({"u1": {"expiration_ts": FUTURE}})
    log = logging.getLogger("test_cleanup_expired")
    result = ce.process_user(c, user("u1"), NOW, log)
    assert result is False
    assert no_calls(c)


def test_no_expiration_set_untouched():
    c = make_client({"u1": {}})
    log = logging.getLogger("test_cleanup_expired")
    result = ce.process_user(c, user("u1"), NOW, log)
    assert result is False
    assert no_calls(c)


def test_attrs_fetch_failure_untouched():
    c = make_client({})
    log = logging.getLogger("test_cleanup_expired")

    def boom(etype, eid, keys=None):
        raise RuntimeError("network down")

    c.get_server_attrs = boom
    result = ce.process_user(c, user("u1"), NOW, log)
    assert result is False
    assert no_calls(c)

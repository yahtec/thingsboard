"""Destinataires du recap : id, exclusions par destinataire, etat de cadence
(spec §5.1 et §6.2)."""
import common


def _client(users, attrs_by_user):
    """TBClient reel dont seuls list_users / get_server_attrs sont mockes.
    On garde le vrai _collect_user_attrs : c'est lui qu'on teste."""
    c = common.TBClient(url="http://test", user="svc@yahtec.com", password="x")
    c.list_users = lambda: users
    c.get_server_attrs = lambda etype, eid, keys=None: dict(attrs_by_user.get(eid, {}))
    c.site_of_devices = lambda profile: {}
    return c


def _user(uid, email, authority="TENANT_ADMIN"):
    return {"id": {"id": uid}, "email": email, "authority": authority,
            "customerId": {"id": None}}


def test_collect_user_attrs_exposes_id_and_exclusions():
    c = _client([_user("u1", "a@yahtec.com")],
                {"u1": {"is_admin": True, "mail_exclude_devices": ["d1", "d2"]}})
    (u,) = c._collect_user_attrs()
    assert u["id"] == "u1"
    assert u["mail_exclude"] == ["d1", "d2"]


def test_exclusions_accept_json_string_and_reject_garbage():
    c = _client([_user("u1", "a@yahtec.com"), _user("u2", "b@yahtec.com"),
                 _user("u3", "c@yahtec.com")],
                {"u1": {"mail_exclude_devices": '["d1"]'},
                 "u2": {"mail_exclude_devices": "pas du json"},
                 "u3": {"mail_exclude_devices": 42}})
    by_email = {u["email"]: u for u in c._collect_user_attrs()}
    assert by_email["a@yahtec.com"]["mail_exclude"] == ["d1"]
    assert by_email["b@yahtec.com"]["mail_exclude"] == []
    assert by_email["c@yahtec.com"]["mail_exclude"] == []


def test_admin_targets_keeps_admins_and_drops_service_account():
    c = _client([_user("u1", "a@yahtec.com"),
                 _user("u2", "svc@yahtec.com"),
                 _user("u3", "p@example.com", "CUSTOMER_USER")],
                {"u1": {"mail_exclude_devices": ["d9"]}})
    targets = c.get_admin_targets()
    assert [t["email"] for t in targets] == ["a@yahtec.com"]
    assert targets[0]["id"] == "u1"
    assert targets[0]["exclude"] == {"d9"}


def test_admin_targets_includes_customer_user_flagged_admin():
    c = _client([_user("u1", "ops@yahtec.com", "CUSTOMER_USER")],
                {"u1": {"is_admin": True}})
    assert [t["email"] for t in c.get_admin_targets()] == ["ops@yahtec.com"]


def test_admin_targets_skips_deactivated_account():
    c = _client([_user("u1", "a@yahtec.com")], {"u1": {"deactivated": True}})
    assert c.get_admin_targets() == []


def test_load_digest_state_always_has_both_keys():
    assert common.load_digest_state(None) == {"last_mail_ts": 0, "last_fast_ts": 0}
    assert common.load_digest_state("corrompu") == {"last_mail_ts": 0, "last_fast_ts": 0}
    assert common.load_digest_state({"last_mail_ts": "5"}) == {"last_mail_ts": 5, "last_fast_ts": 0}


def test_digest_state_round_trip():
    saved = {}
    c = common.TBClient(url="http://test", user="svc", password="x")
    c.get_server_attrs = lambda etype, eid, keys=None: dict(saved.get(eid, {}))
    c.save_server_attrs = lambda etype, eid, kv: saved.setdefault(eid, {}).update(kv)
    c.save_digest_state("u1", {"last_mail_ts": 7, "last_fast_ts": 8})
    assert c.get_digest_state("u1") == {"last_mail_ts": 7, "last_fast_ts": 8}
    assert c.get_digest_state("inconnu") == {"last_mail_ts": 0, "last_fast_ts": 0}

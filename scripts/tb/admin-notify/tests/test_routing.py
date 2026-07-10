import common

DEVICE = "dev-1"
SITE = "site-cust-1"
PARTY_CID = "party-cust-1"


def make_client(users, attrs_by_uid, site_of_dev, canview_by_cid):
    c = common.TBClient(url="http://test", user="svc", password="x")
    c.list_users = lambda: users
    c.site_of_devices = lambda profile: dict(site_of_dev)
    c.get_server_attrs = lambda etype, eid, keys=None: dict(attrs_by_uid.get(eid, {}))
    c.canview_site_ids = lambda cid: set(canview_by_cid.get(cid, []))
    return c


def user(uid, email, authority="CUSTOMER_USER", customer_id=PARTY_CID, cred_enabled=None):
    add = {}
    if cred_enabled is not None:
        add["userCredentialsEnabled"] = cred_enabled
    return {
        "id": {"id": uid},
        "email": email,
        "authority": authority,
        "customerId": {"id": customer_id} if customer_id else None,
        "additionalInfo": add,
    }


def test_canview_derives_recipient():
    c = make_client([user("u1", "syndic@ex.com")], {"u1": {}},
                    {DEVICE: SITE}, {PARTY_CID: [SITE]})
    assert c.get_recipients_for_device(DEVICE) == ["syndic@ex.com"]


def test_deactivated_user_excluded():
    c = make_client([user("u1", "syndic@ex.com")], {"u1": {"deactivated": True}},
                    {DEVICE: SITE}, {PARTY_CID: [SITE]})
    assert c.get_recipients_for_device(DEVICE) == []


def test_credentials_disabled_still_included():
    # Garde de non-regression A1 : userCredentialsEnabled=false ne doit PAS exclure.
    c = make_client([user("u1", "syndic@ex.com", cred_enabled=False)], {"u1": {}},
                    {DEVICE: SITE}, {PARTY_CID: [SITE]})
    assert c.get_recipients_for_device(DEVICE) == ["syndic@ex.com"]


def test_admin_excluded_from_per_device():
    c = make_client([user("u1", "admin@ex.com"), user("u2", "syndic@ex.com")],
                    {"u1": {"is_admin": True}, "u2": {}},
                    {DEVICE: SITE}, {PARTY_CID: [SITE]})
    assert c.get_recipients_for_device(DEVICE) == ["syndic@ex.com"]


def test_yahtec_customer_user_has_no_sites():
    c = make_client([user("u1", "ops@ex.com", customer_id=common.YAHTEC_CID)],
                    {"u1": {}}, {DEVICE: SITE}, {common.YAHTEC_CID: [SITE]})
    assert c.get_recipients_for_device(DEVICE) == []


def test_attrs_fetch_failure_skips_user_fail_closed():
    # I6 : un echec de fetch d'attrs (reseau, 5xx...) ne doit JAMAIS faire
    # comme si l'utilisateur etait {} (fail-open) -> il doit etre exclu de
    # ce run entier (fail-closed), pas traite comme non-admin/non-desactive.
    c = make_client([user("u1", "broken@ex.com"), user("u2", "ok@ex.com")],
                    {}, {DEVICE: SITE}, {PARTY_CID: [SITE]})

    def flaky_attrs(etype, eid, keys=None):
        if eid == "u1":
            raise RuntimeError("network down")
        return {}

    c.get_server_attrs = flaky_attrs
    result = c._collect_user_attrs()
    emails = [u["email"] for u in result]
    assert "broken@ex.com" not in emails
    assert "ok@ex.com" in emails


def test_attrs_fetch_failure_admin_not_spammed_per_device():
    # Meme scenario, mais côté effet observable : si le fetch d'attrs de
    # l'admin echoue, il ne doit PAS se retrouver traite comme non-admin
    # dans le routage per-device (fail-open historique).
    c = make_client([user("admin1", "admin@ex.com")], {}, {DEVICE: SITE}, {PARTY_CID: [SITE]})

    def boom(etype, eid, keys=None):
        raise RuntimeError("network down")

    c.get_server_attrs = boom
    assert c.get_recipients_for_device(DEVICE) == []


def test_admin_emails_excludes_service_account():
    # M14 : svc-tbnotify@ (self.user) est TENANT_ADMIN mais ne doit pas se
    # spammer lui-meme via get_admin_emails.
    c = make_client([
        user("u1", "je@yahtec.com", authority="TENANT_ADMIN"),
        user("svc", "svc-tbnotify@yahtec.com", authority="TENANT_ADMIN"),
    ], {}, {}, {})
    c.user = "svc-tbnotify@yahtec.com"
    assert c.get_admin_emails() == ["je@yahtec.com"]


def test_admin_emails_excludes_service_account_case_insensitive():
    c = make_client([user("svc", "Svc-TBNotify@Yahtec.com", authority="TENANT_ADMIN")], {}, {}, {})
    c.user = "svc-tbnotify@yahtec.com"
    assert c.get_admin_emails() == []

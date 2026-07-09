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

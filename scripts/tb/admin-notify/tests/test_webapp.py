"""Tests webapp.py — gardes et fiabilite (I9, I10, M15, M16 + reactivation).

Contrainte d'environnement : fastapi / jinja2 / itsdangerous ne sont pas
installes dans l'environnement de test (la suite tourne sur un python minimal :
requests + pytest + dotenv). On stubbe donc ces modules dans sys.modules AVANT
d'importer webapp, ce qui permet de tester les VRAIS handlers de route (logique
de garde, cibles de redirection, effets de bord via un TBClient monkeypatche)
sans le framework. Les stubs sont poses via setdefault : sur une machine ou
fastapi est reellement installe, le vrai module est utilise et les memes
assertions tiennent (RedirectResponse.status_code / .headers['location']).
"""
import asyncio
import os
import re
import sys
import types
from pathlib import Path

# ── env requis a l'import de webapp ──────────────────────────────────────────
os.environ.setdefault("TB_URL", "http://test")
os.environ.setdefault("TB_USER", "svc")
os.environ.setdefault("TB_PASS", "x")
os.environ.setdefault("WEB_SECRET", "x" * 64)


# ── stubs fastapi / itsdangerous (poses seulement si absents) ────────────────
def _stub_fastapi():
    fastapi = types.ModuleType("fastapi")

    class _Marker:
        def __init__(self, *a, **k):
            pass

    def _passthrough(*a, **k):
        return _Marker()

    class FastAPI:
        def __init__(self, *a, **k):
            pass

        def _dec(self, *a, **k):
            def deco(fn):
                return fn
            return deco

        get = post = put = delete = patch = _dec

    class HTTPException(Exception):
        def __init__(self, status_code=None, headers=None, **k):
            self.status_code = status_code
            self.headers = headers or {}

    class _Status:
        HTTP_303_SEE_OTHER = 303

    fastapi.FastAPI = FastAPI
    fastapi.Body = _passthrough
    fastapi.Cookie = _passthrough
    fastapi.Depends = _passthrough
    fastapi.Form = _passthrough
    fastapi.HTTPException = HTTPException
    fastapi.Request = object
    fastapi.status = _Status()

    responses = types.ModuleType("fastapi.responses")

    class RedirectResponse:
        def __init__(self, url, status_code=307, headers=None):
            self.url = url
            self.status_code = status_code
            self.headers = {"location": url}
            if headers:
                self.headers.update(headers)

    class HTMLResponse:
        pass

    class JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code

    responses.RedirectResponse = RedirectResponse
    responses.HTMLResponse = HTMLResponse
    responses.JSONResponse = JSONResponse

    templating = types.ModuleType("fastapi.templating")

    class _Env:
        def __init__(self):
            self.filters = {}

    class Jinja2Templates:
        def __init__(self, *a, **k):
            self.env = _Env()

        def TemplateResponse(self, *a, **k):
            return ("template", a, k)

    templating.Jinja2Templates = Jinja2Templates

    sys.modules.setdefault("fastapi", fastapi)
    sys.modules.setdefault("fastapi.responses", responses)
    sys.modules.setdefault("fastapi.templating", templating)


def _stub_itsdangerous():
    its = types.ModuleType("itsdangerous")

    class URLSafeTimedSerializer:
        def __init__(self, *a, **k):
            pass

        def dumps(self, obj):
            import json
            return "sig:" + json.dumps(obj)

        def loads(self, s, max_age=None):
            import json
            return json.loads(s[4:])

    class BadSignature(Exception):
        pass

    class SignatureExpired(Exception):
        pass

    its.URLSafeTimedSerializer = URLSafeTimedSerializer
    its.BadSignature = BadSignature
    its.SignatureExpired = SignatureExpired
    sys.modules.setdefault("itsdangerous", its)


_stub_fastapi()
_stub_itsdangerous()

import requests  # noqa: E402

import webapp  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def http_error(status=400):
    resp = types.SimpleNamespace(status_code=status)
    e = requests.HTTPError(str(status))
    e.response = resp
    return e


class FakeForm:
    """Mime le minimum de l'API starlette FormData utilise par les handlers."""

    def __init__(self, items):
        self._items = list(items)

    def get(self, key, default=None):
        for k, v in self._items:
            if k == key:
                return v
        return default

    def getlist(self, key):
        return [v for k, v in self._items if k == key]

    def multi_items(self):
        return list(self._items)


class FakeRequest:
    def __init__(self, form_data):
        self._form = form_data

    async def form(self):
        return self._form


class FakeTB:
    def __init__(self):
        self.users = {}
        self.deleted = []
        self.updated = []
        self.saved = []                 # (etype, eid, kv)
        self.cred = []                  # (uid, enabled)
        self.reconciled = []
        self.update_user_error = None
        self.save_attrs_error = None
        self.reconcile_error = None
        self.activation_link_value = "http://tb/activate?x=1"

    def get_user(self, uid):
        if uid not in self.users:
            raise http_error(404)
        return dict(self.users[uid])

    def delete_user(self, uid):
        self.deleted.append(uid)

    def update_user(self, u):
        if self.update_user_error:
            raise self.update_user_error
        self.updated.append(dict(u))
        return u

    def save_server_attrs(self, etype, eid, kv):
        if self.save_attrs_error:
            raise self.save_attrs_error
        self.saved.append((etype, eid, dict(kv)))

    def set_credentials_enabled(self, uid, enabled):
        self.cred.append((uid, enabled))

    def get_server_attrs(self, etype, eid, keys=None):
        return {}

    def list_devices_by_profile(self, profile):
        return []

    def reconcile_canview(self, party_cid, desired, fleet):
        if self.reconcile_error:
            raise self.reconcile_error
        self.reconciled.append((party_cid, set(desired), set(fleet)))

    def canview_site_ids(self, cid):
        return set()

    def ensure_party_customer(self, email):
        return "party-cid"

    def create_user(self, payload, send_activation_mail=False):
        return {"id": {"id": "new-uid"}}

    def activation_link(self, uid):
        return self.activation_link_value


def install_tb(monkeypatch, fake):
    monkeypatch.setattr(webapp, "TBClient", lambda *a, **k: fake)


def loc(resp):
    return resp.headers["location"]


R = webapp.ROOT_PATH


def user_obj(uid, email, authority="CUSTOMER_USER"):
    return {"id": {"id": uid}, "email": email, "authority": authority}


# ── I10 : gardes account_delete ──────────────────────────────────────────────

def test_delete_blocks_tenant_admin(monkeypatch):
    fake = FakeTB()
    fake.users["adm"] = user_obj("adm", "je@yahtec.com", "TENANT_ADMIN")
    install_tb(monkeypatch, fake)
    resp = webapp.account_delete("adm", user={"u": "ops@yahtec.com"})
    assert resp.status_code == 303
    assert loc(resp) == f"{R}/?error=admin_no_delete"
    assert fake.deleted == []


def test_delete_blocks_self(monkeypatch):
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "Ops@Yahtec.com", "CUSTOMER_USER")
    install_tb(monkeypatch, fake)
    resp = webapp.account_delete("u1", user={"u": "ops@yahtec.com"})
    assert loc(resp) == f"{R}/?error=cannot_delete_self"
    assert fake.deleted == []


def test_delete_allows_customer_user(monkeypatch):
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "party@ex.com", "CUSTOMER_USER")
    install_tb(monkeypatch, fake)
    resp = webapp.account_delete("u1", user={"u": "ops@yahtec.com"})
    assert loc(resp) == f"{R}/?deleted=1"
    assert fake.deleted == ["u1"]


def test_delete_fail_closed_when_user_missing(monkeypatch):
    fake = FakeTB()  # aucun user -> get_user leve 404
    install_tb(monkeypatch, fake)
    resp = webapp.account_delete("ghost", user={"u": "ops@yahtec.com"})
    assert loc(resp) == f"{R}/?error=not_found"
    assert fake.deleted == []


def test_delete_fail_closed_unknown_authority(monkeypatch):
    fake = FakeTB()
    fake.users["u1"] = {"id": {"id": "u1"}, "email": "x@ex.com"}  # authority absente
    install_tb(monkeypatch, fake)
    resp = webapp.account_delete("u1", user={"u": "ops@yahtec.com"})
    assert loc(resp).startswith(f"{R}/?error=")
    assert "deleted=1" not in loc(resp)
    assert fake.deleted == []


# ── Reactivation purge expiration_ts (addition A) ────────────────────────────

def test_reactivate_clears_expiration_ts(monkeypatch):
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "party@ex.com", "CUSTOMER_USER")
    install_tb(monkeypatch, fake)
    webapp._set_account_active("u1", True, "ops@yahtec.com")
    assert fake.cred == [("u1", True)]
    saved_kv = {}
    for etype, eid, kv in fake.saved:
        if eid == "u1":
            saved_kv.update(kv)
    assert saved_kv.get("deactivated") is False
    assert saved_kv.get("expiration_ts") == 0


def test_deactivate_does_not_set_expiration(monkeypatch):
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "party@ex.com", "CUSTOMER_USER")
    install_tb(monkeypatch, fake)
    webapp._set_account_active("u1", False, "ops@yahtec.com")
    assert fake.cred == [("u1", False)]
    saved_kv = {}
    for etype, eid, kv in fake.saved:
        if eid == "u1":
            saved_kv.update(kv)
    assert saved_kv.get("deactivated") is True
    assert "expiration_ts" not in saved_kv


# ── I9 : _send_invitation remonte les echecs, pas de mail trompeur ───────────

def _attrs():
    return {"droit_acces": "lecture", "is_admin": False, "chaufferies": []}


def test_invitation_attrs_failure_no_mail(monkeypatch):
    fake = FakeTB()
    fake.save_attrs_error = http_error(500)
    sent = []
    monkeypatch.setattr(webapp, "send_mail", lambda to, subject, html, text=None: sent.append(to))
    ok, msg = webapp._send_invitation(fake, {"email": "p@ex.com", "first_name": "", "last_name": "", "societe": ""}, _attrs())
    assert ok is False
    assert sent == []


def test_invitation_canview_failure_no_mail(monkeypatch):
    fake = FakeTB()
    fake.reconcile_error = http_error(500)
    sent = []
    monkeypatch.setattr(webapp, "send_mail", lambda to, subject, html, text=None: sent.append(to))
    ok, msg = webapp._send_invitation(fake, {"email": "p@ex.com", "first_name": "", "last_name": "", "societe": ""}, _attrs())
    assert ok is False
    assert sent == []


def test_invitation_success_sends_mail(monkeypatch):
    fake = FakeTB()
    sent = []
    monkeypatch.setattr(webapp, "send_mail", lambda to, subject, html, text=None: sent.append(to))
    ok, msg = webapp._send_invitation(fake, {"email": "p@ex.com", "first_name": "A", "last_name": "B", "societe": ""}, _attrs())
    assert ok is True
    assert sent == [["p@ex.com"]]


# ── M15 : account_edit_save email dupliqué → redirect propre ─────────────────

def test_edit_duplicate_email_redirects(monkeypatch):
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "old@ex.com", "CUSTOMER_USER")
    fake.update_user_error = http_error(400)
    install_tb(monkeypatch, fake)
    form = FakeForm([("first_name", "A"), ("last_name", "B"),
                     ("email", "dup@ex.com"), ("droit_acces", "lecture")])
    resp = asyncio.run(webapp.account_edit_save("u1", FakeRequest(form), user={"u": "ops@yahtec.com"}))
    assert resp.status_code == 303
    assert loc(resp) == f"{R}/accounts/u1/edit?error=email_invalid"


# ── M16 : invite-temp date invalide → aucun compte permanent ─────────────────

def test_invite_temp_bad_date_no_account(monkeypatch):
    called = []
    monkeypatch.setattr(webapp, "_send_invitation", lambda *a, **k: called.append(a) or (True, "ok"))
    monkeypatch.setattr(webapp, "TBClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("TBClient ne doit pas etre instancie")))
    form = FakeForm([("email", "p@ex.com"), ("expiration", "pas-une-date"),
                     ("droit_acces", "lecture")])
    resp = asyncio.run(webapp.invite_temp_post(FakeRequest(form), user={"u": "ops@yahtec.com"}))
    assert loc(resp) == f"{R}/invite-temp?error=bad_expiration"
    assert called == []


def test_invite_temp_missing_date_no_account(monkeypatch):
    called = []
    monkeypatch.setattr(webapp, "_send_invitation", lambda *a, **k: called.append(a) or (True, "ok"))
    form = FakeForm([("email", "p@ex.com"), ("droit_acces", "lecture")])
    resp = asyncio.run(webapp.invite_temp_post(FakeRequest(form), user={"u": "ops@yahtec.com"}))
    assert loc(resp) == f"{R}/invite-temp?error=bad_expiration"
    assert called == []


def test_invite_temp_valid_date_proceeds(monkeypatch):
    captured = {}

    def fake_send(tb, invitee, attrs):
        captured["attrs"] = attrs
        return True, "ok"

    monkeypatch.setattr(webapp, "_send_invitation", fake_send)
    fake = FakeTB()
    install_tb(monkeypatch, fake)
    form = FakeForm([("email", "p@ex.com"), ("expiration", "2027-01-01"),
                     ("droit_acces", "lecture")])
    resp = asyncio.run(webapp.invite_temp_post(FakeRequest(form), user={"u": "ops@yahtec.com"}))
    assert loc(resp) == f"{R}/?invited=1"
    assert captured["attrs"].get("expiration_ts")


# ── I11 : page comptes hoiste les fetchs fleet-wide (pas O(users x devices)) ─
#
# Avant fix : _user_row appelait _list_chaufferies(tb) (list_devices_by_profile
# + 1 GET attrs par device) PLUS un GET site_customer_id par device, POUR
# CHAQUE user CUSTOMER_USER non-yahtec de la page -> ~220+ round-trips
# sequentiels pour 20 users x 5 devices, croissance O(users x devices).
# Fix : accounts_index calcule chaufferies + site_of_dev UNE FOIS et les passe
# a _user_row.

class FleetFakeTB(FakeTB):
    """FakeTB + comptage des appels fleet-wide (list_devices_by_profile,
    get_server_attrs sur DEVICE, canview_site_ids) pour prouver le hoisting."""

    def __init__(self, devices, site_of_dev=None, canview=None):
        super().__init__()
        self._devices = devices
        self._site_of_dev = dict(site_of_dev or {})
        self._canview = set(canview or [])
        self.list_devices_calls = 0
        self.device_attr_calls = 0
        self.canview_calls = 0

    def list_devices_by_profile(self, profile):
        self.list_devices_calls += 1
        return list(self._devices)

    def get_server_attrs(self, etype, eid, keys=None):
        if etype == "DEVICE":
            self.device_attr_calls += 1
            if keys and "site_customer_id" in keys:
                return {"site_customer_id": self._site_of_dev.get(eid)}
            return {}
        return {}

    def site_of_devices(self, profile):
        # Mirroir de common.TBClient.site_of_devices : list_devices_by_profile
        # + 1 GET par device, via CE fake (donc comptabilise dans les compteurs).
        out = {}
        for d in self.list_devices_by_profile(profile):
            did = d["id"]["id"]
            scid = self.get_server_attrs("DEVICE", did, ["site_customer_id"]).get("site_customer_id")
            if scid:
                out[did] = scid
        return out

    def canview_site_ids(self, cid):
        self.canview_calls += 1
        return set(self._canview)


def _devices(*ids):
    return [{"id": {"id": i}, "name": i} for i in ids]


def test_user_row_precomputed_avoids_per_device_calls(monkeypatch):
    fake = FleetFakeTB(_devices("d1", "d2"), site_of_dev={"d1": "siteA", "d2": "siteB"},
                       canview={"siteA"})
    u = user_obj("u1", "party@ex.com", "CUSTOMER_USER")
    u["customerId"] = {"id": "party-cid"}
    chaufferies = webapp._list_chaufferies(fake)
    site_of_dev = fake.site_of_devices(webapp.PROFILE)
    fake.list_devices_calls = 0
    fake.device_attr_calls = 0
    row = webapp._user_row(fake, u, chaufferies=chaufferies, site_of_dev=site_of_dev)
    assert fake.list_devices_calls == 0
    assert fake.device_attr_calls == 0
    assert fake.canview_calls == 1
    assert row["chaufferies"] == ["d1"]


def test_user_row_output_identical_hoisted_vs_lazy(monkeypatch):
    fake = FleetFakeTB(_devices("d1", "d2"), site_of_dev={"d1": "siteA", "d2": "siteB"},
                       canview={"siteA"})
    u = user_obj("u1", "party@ex.com", "CUSTOMER_USER")
    u["customerId"] = {"id": "party-cid"}
    row_lazy = webapp._user_row(fake, u)
    chaufferies = webapp._list_chaufferies(fake)
    site_of_dev = fake.site_of_devices(webapp.PROFILE)
    row_hoisted = webapp._user_row(fake, u, chaufferies=chaufferies, site_of_dev=site_of_dev)
    assert row_lazy == row_hoisted


def test_accounts_index_computes_fleet_data_once(monkeypatch):
    fake = FleetFakeTB(_devices("d1"), site_of_dev={"d1": "siteA"}, canview={"siteA"})
    users = []
    for i in range(6):
        uid = f"u{i}"
        uu = user_obj(uid, f"p{i}@ex.com", "CUSTOMER_USER")
        uu["customerId"] = {"id": f"party-{i}"}
        users.append(uu)
    fake.list_all_users = lambda customer_id=None: users
    install_tb(monkeypatch, fake)

    calls = {"n": 0}
    orig_list_chaufferies = webapp._list_chaufferies

    def counting(tb):
        calls["n"] += 1
        return orig_list_chaufferies(tb)

    monkeypatch.setattr(webapp, "_list_chaufferies", counting)

    sess = webapp._make_session({"u": "ops@yahtec.com"})
    webapp.accounts_index(types.SimpleNamespace(), session=sess)

    assert calls["n"] == 1
    # Hoisted : list_devices_by_profile appele au plus une fois par source
    # (_list_chaufferies + site_of_devices), PAS une fois par user (6 users).
    assert fake.list_devices_calls <= 2
    assert fake.device_attr_calls <= 3
    # canview_site_ids reste per-user (attendu : CanView differe par party).
    assert fake.canview_calls == 6


# ── Filtrage des mails par destinataire (spec §6.2) ─────────────────────────

def _fleet(fake, ids):
    fake.list_devices_by_profile = lambda profile: [
        {"id": {"id": i}, "name": i} for i in ids]


def test_edit_save_writes_mail_exclusions_for_a_tenant_admin(monkeypatch):
    """Coche d1 seulement -> d2 et d3 sont exclus des mails."""
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "a@yahtec.com", "TENANT_ADMIN")
    _fleet(fake, ["d1", "d2", "d3"])
    install_tb(monkeypatch, fake)
    form = FakeForm([("first_name", "A"), ("last_name", "B"),
                     ("email", "a@yahtec.com"), ("droit_acces", "admin"),
                     ("mail_devices_present", "1"), ("mail_devices", "d1")])
    asyncio.run(webapp.account_edit_save("u1", FakeRequest(form), user={"u": "ops@yahtec.com"}))
    (_etype, _eid, kv) = [s for s in fake.saved if "mail_exclude_devices" in s[2]][-1]
    assert sorted(kv["mail_exclude_devices"]) == ["d2", "d3"]


def test_unchecking_everything_mutes_the_account(monkeypatch):
    """Aucune chaufferie cochee = perimetre vide = mails coupes. Le POST porte
    la sentinelle : le bloc de cases ETAIT bien dans le formulaire, l'operateur
    a donc vraiment voulu le silence. Sans elle, c'est le cas "bloc absent" du
    test suivant — deux intentions opposees qui produisaient jusqu'ici le meme
    POST (I2)."""
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "a@yahtec.com", "TENANT_ADMIN")
    _fleet(fake, ["d1", "d2"])
    install_tb(monkeypatch, fake)
    form = FakeForm([("email", "a@yahtec.com"), ("droit_acces", "admin"),
                     ("mail_devices_present", "1")])
    asyncio.run(webapp.account_edit_save("u1", FakeRequest(form), user={"u": "ops@yahtec.com"}))
    (_etype, _eid, kv) = [s for s in fake.saved if "mail_exclude_devices" in s[2]][-1]
    assert sorted(kv["mail_exclude_devices"]) == ["d1", "d2"]


def test_non_admin_account_never_gets_mail_exclusions(monkeypatch):
    """Le champ est absent du formulaire d'un non-admin : ne rien ecrire,
    sinon on le rendrait muet par accident."""
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "p@example.com", "CUSTOMER_USER")
    _fleet(fake, ["d1", "d2"])
    install_tb(monkeypatch, fake)
    form = FakeForm([("email", "p@example.com"), ("droit_acces", "lecture")])
    asyncio.run(webapp.account_edit_save("u1", FakeRequest(form), user={"u": "ops@yahtec.com"}))
    assert not any("mail_exclude_devices" in kv for _e, _i, kv in fake.saved)


def test_promoting_an_account_to_admin_does_not_mute_it(monkeypatch):
    """I2 : la fiche servie AVANT la promotion n'affichait pas le bloc de
    cases (il est conditionne a `row.is_admin`), donc le POST qui promeut
    lecture -> admin ne porte ni `mail_devices` ni la sentinelle. Sans la
    sentinelle on ecrivait "tout le parc exclu" : le compte fraichement promu
    ne recevait plus jamais rien, sans message ni log. Bloc absent = ne rien
    ecrire, l'operateur reglera ses chaufferies a la reouverture."""
    fake = FakeTB()
    fake.users["u1"] = user_obj("u1", "p@example.com", "CUSTOMER_USER")
    _fleet(fake, ["d1", "d2"])
    install_tb(monkeypatch, fake)
    form = FakeForm([("email", "p@example.com"), ("droit_acces", "admin")])
    asyncio.run(webapp.account_edit_save("u1", FakeRequest(form), user={"u": "ops@yahtec.com"}))
    assert not any("mail_exclude_devices" in kv for _e, _i, kv in fake.saved)
    # ... et le compte est bien devenu admin : c'est la promotion qui a eu lieu,
    # pas un abandon du POST.
    assert [kv for _e, _i, kv in fake.saved if "is_admin" in kv][-1]["is_admin"] is True


def test_the_mail_block_sentinel_lives_inside_the_admin_only_block():
    """La sentinelle ne vaut que si elle est DANS le `{% if row.is_admin %}` :
    posee en dehors, elle serait toujours postee et le cas "bloc absent"
    redeviendrait indistinguable de "rien coche". C'est le seul couplage entre
    le gabarit et le handler, il merite d'etre epingle."""
    tpl = (Path(webapp.__file__).parent / "templates" / "account_edit.html").read_text(encoding="utf-8")
    start = tpl.index("{% if row.is_admin %}")
    depth, end = 0, None
    for m in re.finditer(r"{%-?\s*(endif|if)[\s%]", tpl[start:]):
        depth += 1 if m.group(1) == "if" else -1
        if depth == 0:
            end = start + m.start()
            break
    assert end is not None, "bloc {% if row.is_admin %} non ferme"
    sentinel = 'name="mail_devices_present"'
    assert sentinel in tpl[start:end]
    assert sentinel not in tpl[:start] + tpl[end:]

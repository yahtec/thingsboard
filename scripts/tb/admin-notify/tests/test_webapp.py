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
import sys
import types

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

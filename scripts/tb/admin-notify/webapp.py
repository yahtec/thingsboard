#!/usr/bin/env python3
"""Mini admin web app TDUO.

- /                       → Gestion des comptes (table users + bandeau)
- /accounts/<uid>/edit    → fiche utilisateur
- /accounts/<uid>/delete  → suppression (POST)
- /invite                 → formulaire multi-invitations
- /invite-temp            → invitation temporaire (un user, date d'expiration)
- /profile                → fiche utilisateur (tous les TB users)

Auth: TB /api/auth/login + TENANT_ADMIN ou CUSTOMER_USER+is_admin.
Session cookie signé (itsdangerous), 12h.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import Body, Cookie, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from common import (MAIL_EXCLUDE_ATTR, MailConfig, TBClient,  # noqa: E402
                    load_exclude_list, send_mail)

TB_URL = os.environ["TB_URL"].rstrip("/")
TB_PUBLIC_URL = os.environ.get("TB_PUBLIC_URL", "https://thingsboard.tsmart.fr").rstrip("/")
CUSTOMER_ID = os.environ.get("TB_CUSTOMER_ID")
PROFILE = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
KIOSK_DASH_ID = os.environ.get("KIOSK_DASH_ID", "0964da30-3e56-11f1-bbfe-e1395562cba0")
KIOSK_ADDITIONAL_INFO = {
    "homeDashboardId": KIOSK_DASH_ID,
    "homeDashboardHideToolbar": True,
    "defaultDashboardId": KIOSK_DASH_ID,
    # False : JAMAIS True pour un intervenant. True -> /dashboard/{id} SINGULIER = fullscreen
    # standalone SANS yahtec-nav (barre TB native) ; False -> /dashboards/{id} PLURIEL AVEC
    # yahtec-nav. Cf spec chrome 3 roles. Landing conserve via defaultDashboardId+homeDashboardId.
    "defaultDashboardFullscreen": False,
}
SECRET = os.environ["WEB_SECRET"].encode()
SESSION_TTL = 12 * 3600
COOKIE = "tbnotify_sess"
COOKIE_PROFILE = "tbnotify_profile"
ROOT_PATH = os.environ.get("WEB_ROOT_PATH", "/admin-notify")

# Attributs custom user (SERVER_SCOPE)
USER_ATTRS = [
    "is_admin", "societe", "droit_acces",
    "access_rapport", "access_retroview", "access_spherys",
    "chaufferies", "expiration_ts", "deactivated", MAIL_EXCLUDE_ATTR,
]
ROLES = [
    ("lecture", "Lecture"),
    ("ecriture", "Lecture + Écriture"),
    ("admin", "Admin"),
]

serializer = URLSafeTimedSerializer(SECRET, salt="tb-notify-session")
serializer_profile = URLSafeTimedSerializer(SECRET, salt="tb-notify-profile")
app = FastAPI(root_path=ROOT_PATH, docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def _fmt_ts(value, fmt: str) -> str:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    if not ts:
        return ""
    return time.strftime(fmt, time.localtime(ts / 1000))


templates.env.filters["ts_to_date"] = lambda v: _fmt_ts(v, "%d/%m/%Y %H:%M")
templates.env.filters["ts_to_date_only"] = lambda v: _fmt_ts(v, "%d/%m/%Y")
templates.env.filters["ts_to_iso"] = lambda v: _fmt_ts(v, "%Y-%m-%d")


# ─── Session helpers ────────────────────────────────────────────────────────

def _make_session(payload: dict) -> str:
    return serializer.dumps(payload)


def _read_session(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return serializer.loads(token, max_age=SESSION_TTL)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def require_user(session: str | None = Cookie(default=None, alias=COOKIE)) -> dict:
    sess = _read_session(session)
    if not sess:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": f"{ROOT_PATH}/login"})
    return sess


def _is_admin_user(token: str) -> tuple[bool, str | None]:
    try:
        me = requests.get(f"{TB_URL}/api/auth/user",
                          headers={"X-Authorization": f"Bearer {token}"}, timeout=15).json()
    except requests.RequestException:
        return False, None
    authority = me.get("authority")
    email = me.get("email")
    if authority == "TENANT_ADMIN":
        return True, email
    if authority != "CUSTOMER_USER":
        return False, email
    uid = me.get("id", {}).get("id")
    try:
        attrs = requests.get(
            f"{TB_URL}/api/plugins/telemetry/USER/{uid}/values/attributes/SERVER_SCOPE?keys=is_admin",
            headers={"X-Authorization": f"Bearer {token}"}, timeout=15,
        ).json()
    except requests.RequestException:
        return False, email
    if any(a.get("key") == "is_admin" and a.get("value") is True for a in attrs):
        return True, email
    return False, email


def _set_session_cookie(resp, request: Request, email: str) -> None:
    sess = _make_session({"u": email, "exp": int(time.time()) + SESSION_TTL})
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(COOKIE, sess, max_age=SESSION_TTL, httponly=True, samesite="lax",
                    secure=secure, path=ROOT_PATH)


# ─── Auth routes ────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, error: str | None = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "root": ROOT_PATH})


@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        r = requests.post(f"{TB_URL}/api/auth/login",
                          json={"username": username, "password": password}, timeout=15)
    except requests.RequestException:
        return RedirectResponse(f"{ROOT_PATH}/login?error=tb_unreachable", status_code=303)
    if r.status_code != 200:
        return RedirectResponse(f"{ROOT_PATH}/login?error=invalid", status_code=303)
    token = r.json().get("token")
    ok, email = _is_admin_user(token)
    if not ok or not email:
        return RedirectResponse(f"{ROOT_PATH}/login?error=forbidden", status_code=303)
    resp = RedirectResponse(f"{ROOT_PATH}/", status_code=303)
    _set_session_cookie(resp, request, email)
    return resp


@app.post("/login-jwt")
def login_jwt(request: Request, payload: dict = Body(...)):
    token = (payload or {}).get("token") or ""
    if not token or not token.startswith("ey"):
        return JSONResponse({"ok": False, "error": "missing_token"}, status_code=400)
    ok, email = _is_admin_user(token)
    if not ok or not email:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    resp = JSONResponse({"ok": True, "email": email})
    _set_session_cookie(resp, request, email)
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(f"{ROOT_PATH}/login", status_code=303)
    resp.delete_cookie(COOKIE, path=ROOT_PATH)
    return resp


# ─── Profil utilisateur (tous les TB users authentifiés) ────────────────────

def _validate_tb_user(token: str) -> dict | None:
    """Valide un JWT TB, retourne le user object ou None. Pas de check admin."""
    if not token or not token.startswith("ey"):
        return None
    try:
        r = requests.get(f"{TB_URL}/api/auth/user",
                         headers={"X-Authorization": f"Bearer {token}"}, timeout=15)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    j = r.json()
    if not j.get("email") or not j.get("id", {}).get("id"):
        return None
    return j


def _make_profile_session(payload: dict) -> str:
    return serializer_profile.dumps(payload)


def _read_profile_session(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return serializer_profile.loads(token, max_age=SESSION_TTL)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def _set_profile_cookie(resp, request: Request, payload: dict) -> None:
    sess = _make_profile_session(payload)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(COOKIE_PROFILE, sess, max_age=SESSION_TTL, httponly=True,
                    samesite="lax", secure=secure, path=ROOT_PATH)


def require_profile_user(request: Request,
                         token: str | None = Cookie(default=None, alias=COOKIE_PROFILE)) -> dict:
    sess = _read_profile_session(token)
    if not sess:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER,
                            headers={"Location": f"{ROOT_PATH}/profile"})
    return sess


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, saved: int = 0, error: str | None = None,
                 token: str | None = Cookie(default=None, alias=COOKIE_PROFILE)):
    sess = _read_profile_session(token)
    if not sess:
        # Auto-login via TB JWT depuis localStorage (même origine).
        return templates.TemplateResponse("auto_login_profile.html",
                                          {"request": request, "root": ROOT_PATH})
    tb = TBClient()
    try:
        u = tb.get_user(sess["uid"])
    except requests.HTTPError:
        # session valide mais user introuvable → repart en auto-login
        resp = RedirectResponse(f"{ROOT_PATH}/profile", status_code=303)
        resp.delete_cookie(COOKIE_PROFILE, path=ROOT_PATH)
        return resp
    return templates.TemplateResponse("profile.html", {
        "request": request, "root": ROOT_PATH, "tb_home": TB_PUBLIC_URL,
        "sess": sess, "u": u, "saved": bool(saved), "error": error,
    })


@app.post("/profile/login-jwt")
def profile_login_jwt(request: Request, payload: dict = Body(...)):
    me = _validate_tb_user((payload or {}).get("token") or "")
    if not me:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    resp = JSONResponse({"ok": True})
    _set_profile_cookie(resp, request, {
        "u": me["email"], "uid": me["id"]["id"], "authority": me.get("authority"),
    })
    return resp


@app.post("/profile/save")
async def profile_save(request: Request,
                       sess: dict = Depends(require_profile_user)):
    form = await request.form()
    first_name = (form.get("first_name") or "").strip()
    last_name = (form.get("last_name") or "").strip()
    new_email = (form.get("email") or "").strip().lower()
    curr_pw = form.get("current_password") or ""
    new_pw = form.get("new_password") or ""
    new_pw2 = form.get("new_password_confirm") or ""

    tb = TBClient()
    try:
        u = tb.get_user(sess["uid"])
    except requests.HTTPError:
        return RedirectResponse(f"{ROOT_PATH}/profile?error=user_not_found", status_code=303)

    # 1) Identité (firstName/lastName/email) via TBClient (TENANT_ADMIN).
    u["firstName"] = first_name or None
    u["lastName"] = last_name or None
    if new_email:
        u["email"] = new_email
    try:
        tb.update_user(u)
    except requests.HTTPError as e:
        msg = "email_invalid" if e.response.status_code == 400 else f"tb_{e.response.status_code}"
        return RedirectResponse(f"{ROOT_PATH}/profile?error={msg}", status_code=303)

    # 2) Mot de passe (si demandé) : login avec curr_pw → /api/auth/changePassword.
    if new_pw or new_pw2 or curr_pw:
        if not curr_pw or not new_pw or new_pw != new_pw2:
            return RedirectResponse(f"{ROOT_PATH}/profile?error=password_mismatch", status_code=303)
        # On utilise l'email courant (peut avoir changé juste avant → on relit u après update)
        login_email = u.get("email") or sess["u"]
        try:
            r = requests.post(f"{TB_URL}/api/auth/login",
                              json={"username": login_email, "password": curr_pw}, timeout=15)
        except requests.RequestException:
            return RedirectResponse(f"{ROOT_PATH}/profile?error=tb_unreachable", status_code=303)
        if r.status_code != 200:
            return RedirectResponse(f"{ROOT_PATH}/profile?error=current_password_wrong", status_code=303)
        jwt = r.json().get("token")
        try:
            r2 = requests.post(f"{TB_URL}/api/auth/changePassword",
                               headers={"X-Authorization": f"Bearer {jwt}",
                                        "Content-Type": "application/json"},
                               json={"currentPassword": curr_pw, "newPassword": new_pw},
                               timeout=15)
        except requests.RequestException:
            return RedirectResponse(f"{ROOT_PATH}/profile?error=tb_unreachable", status_code=303)
        if r2.status_code != 200:
            try:
                msg = (r2.json() or {}).get("message", "")[:120]
            except ValueError:
                msg = ""
            return RedirectResponse(f"{ROOT_PATH}/profile?error=" + (msg or "password_rejected"),
                                    status_code=303)

    # Refresh cookie (email potentiellement changé)
    resp = RedirectResponse(f"{ROOT_PATH}/profile?saved=1", status_code=303)
    _set_profile_cookie(resp, request, {
        "u": u.get("email") or sess["u"], "uid": sess["uid"],
        "authority": sess.get("authority"),
    })
    return resp


@app.get("/profile/logout")
def profile_logout(request: Request):
    resp = RedirectResponse(f"{ROOT_PATH}/profile", status_code=303)
    resp.delete_cookie(COOKIE_PROFILE, path=ROOT_PATH)
    return resp


# ─── Comptes ────────────────────────────────────────────────────────────────

def _user_row(tb: TBClient, u: dict, chaufferies: list[dict] | None = None,
              site_of_dev: dict | None = None) -> dict:
    """`chaufferies` (sortie de `_list_chaufferies`) et `site_of_dev` (map
    device_id -> site_customer_id, cf `TBClient.site_of_devices`) peuvent etre
    precalcules par l'appelant et reutilises pour TOUTES les lignes d'une
    meme page (I11) : sans ca, chaque appel refaisait un `_list_chaufferies`
    (list_devices_by_profile + 1 GET/attrs par device) PLUS un GET
    site_customer_id par device, PAR user -> O(users x devices) round-trips
    REST sequentiels (~220+ pour 20 users x 5 devices). Si omis (autres
    appelants a faible cardinalite, ex. account_edit sur un seul user), on
    retombe sur le calcul paresseux d'origine -> sortie identique."""
    uid = u["id"]["id"]
    attrs = tb.get_server_attrs("USER", uid, USER_ATTRS)
    last_login = None
    add = u.get("additionalInfo") or {}
    if isinstance(add, dict):
        last_login = add.get("lastLoginTs")
    is_tenant_admin = u.get("authority") == "TENANT_ADMIN"
    is_admin_attr = bool(attrs.get("is_admin")) or is_tenant_admin
    # Pre-cochage CanView-only (remplace l'ancienne lecture de l'attribut
    # 'chaufferies' du user, qui n'est plus la source de verite). Pour un
    # party-customer dedie (CUSTOMER_USER hors YAHTEC_CID), on derive les
    # chaufferies visibles depuis les relations CanView du party-customer
    # vers les site-customers. Tenant-admin / user sans party dedie ->
    # aucune pre-selection RBAC (comportement actuel).
    party_cid = (u.get("customerId") or {}).get("id")
    chaufferies_ids: list[str] = []
    if u.get("authority") == "CUSTOMER_USER" and party_cid and party_cid != YAHTEC_CID:
        site_ids = tb.canview_site_ids(party_cid)
        fleet = chaufferies if chaufferies is not None else _list_chaufferies(tb)
        dev_site = site_of_dev if site_of_dev is not None else tb.site_of_devices(PROFILE)
        for dev in fleet:
            sc = dev_site.get(dev["id"])
            if sc in site_ids:
                chaufferies_ids.append(dev["id"])
    return {
        "id": uid,
        "first_name": u.get("firstName") or "",
        "last_name": u.get("lastName") or "",
        "email": u.get("email") or "",
        "societe": attrs.get("societe") or "",
        "is_admin": is_admin_attr,
        "is_tenant_admin": is_tenant_admin,
        "last_login_ts": last_login,
        "created_ts": u.get("createdTime"),
        "expiration_ts": attrs.get("expiration_ts"),
        "droit_acces": attrs.get("droit_acces") or ("admin" if is_admin_attr else "lecture"),
        "access_rapport": bool(attrs.get("access_rapport")),
        "access_retroview": bool(attrs.get("access_retroview")),
        "access_spherys": bool(attrs.get("access_spherys")),
        "chaufferies": chaufferies_ids,
        "deactivated": bool(attrs.get("deactivated")),
        "mail_exclude": load_exclude_list(attrs.get(MAIL_EXCLUDE_ATTR)),
    }


def _list_chaufferies(tb: TBClient) -> list[dict]:
    devices = tb.list_devices_by_profile(PROFILE)
    rows = []
    for d in devices:
        attrs = tb.get_server_attrs("DEVICE", d["id"]["id"], ["nom_residence", "nom_alternatif", "adresse"])
        display = attrs.get("nom_residence") or attrs.get("nom_alternatif") or d["name"]
        rows.append({"id": d["id"]["id"], "name": d["name"], "display": display, "address": attrs.get("adresse") or ""})
    rows.sort(key=lambda r: r["display"].lower())
    return rows


YAHTEC_CID = "2e521d10-3e5d-11f1-bbfe-e1395562cba0"


def _sync_canview(tb: TBClient, party_cid: str, droit: str, device_ids) -> None:
    """Réconcilie les CanView du party-customer vers les site-customers.
    droit=='admin' -> toutes les chaufferies du parc ; sinon celles cochées."""
    fleet = {}
    for d in tb.list_devices_by_profile(PROFILE):
        scid = tb.get_server_attrs("DEVICE", d["id"]["id"], ["site_customer_id"]).get("site_customer_id")
        if scid:
            fleet[d["id"]["id"]] = scid
    fleet_site_ids = set(fleet.values())
    if droit == "admin":
        desired = fleet_site_ids
    else:
        desired = {fleet[did] for did in (device_ids or []) if did in fleet}
    tb.reconcile_canview(party_cid, desired, fleet_site_ids)


@app.get("/", response_class=HTMLResponse)
def accounts_index(request: Request, saved: int = 0, invited: int = 0,
                   deleted: int = 0, error: str | None = None,
                   session: str | None = Cookie(default=None, alias=COOKIE)):
    sess = _read_session(session)
    if not sess:
        return templates.TemplateResponse("auto_login.html", {"request": request, "root": ROOT_PATH})
    tb = TBClient()
    users = tb.list_all_users(CUSTOMER_ID)
    # I11 : calculer les donnees fleet-wide (chaufferies + device->site) UNE
    # SEULE FOIS pour toute la page, au lieu d'un recalcul complet par ligne
    # (cf revue 2026-07-10, #11 : O(users x devices) round-trips REST).
    chaufferies = _list_chaufferies(tb)
    site_of_dev = tb.site_of_devices(PROFILE)
    rows = [_user_row(tb, u, chaufferies=chaufferies, site_of_dev=site_of_dev) for u in users]
    rows.sort(key=lambda r: (not r["is_admin"], (r["last_name"] or "").lower(), (r["first_name"] or "").lower()))
    return templates.TemplateResponse("accounts.html", {
        "request": request, "user": sess, "rows": rows, "root": ROOT_PATH,
        "tb_home": TB_PUBLIC_URL, "saved": bool(saved), "invited": int(invited or 0),
        "deleted": int(deleted or 0), "error": error,
    })


@app.get("/accounts/{uid}/edit", response_class=HTMLResponse)
def account_edit(uid: str, request: Request, saved: int = 0, error: str | None = None,
                 user: dict = Depends(require_user)):
    tb = TBClient()
    try:
        u = tb.get_user(uid)
    except requests.HTTPError:
        return RedirectResponse(f"{ROOT_PATH}/?error=not_found", status_code=303)
    # Meme donnees fleet-wide que accounts_index (I11), calculees ici une
    # seule fois et reutilisees pour la ligne ET le dropdown chaufferies du
    # template (evite de refaire _list_chaufferies deux fois pour ce user).
    chaufferies = _list_chaufferies(tb)
    site_of_dev = tb.site_of_devices(PROFILE)
    row = _user_row(tb, u, chaufferies=chaufferies, site_of_dev=site_of_dev)
    # On stocke les EXCLUSIONS mais on affiche les chaufferies SUIVIES : une
    # chaufferie ajoutee plus tard est donc suivie par defaut (spec §6.2).
    excluded = set(row["mail_exclude"])
    mail_followed = [c["id"] for c in chaufferies if c["id"] not in excluded]
    return templates.TemplateResponse("account_edit.html", {
        "request": request, "user": user, "root": ROOT_PATH,
        "row": row, "chaufferies": chaufferies, "mail_followed": mail_followed,
        "roles": ROLES, "saved": bool(saved), "error": error,
    })


@app.post("/accounts/{uid}/edit")
async def account_edit_save(uid: str, request: Request, user: dict = Depends(require_user)):
    form = await request.form()
    tb = TBClient()
    try:
        u = tb.get_user(uid)
    except requests.HTTPError:
        return RedirectResponse(f"{ROOT_PATH}/?error=not_found", status_code=303)

    u["firstName"] = (form.get("first_name") or "").strip() or None
    u["lastName"] = (form.get("last_name") or "").strip() or None
    new_email = (form.get("email") or "").strip()
    if new_email:
        u["email"] = new_email
    try:
        tb.update_user(u)
    except requests.HTTPError as e:
        # M15 : email dupliqué / invalide -> pas de 500 brut dans l'iframe.
        # Meme traitement que profile_save.
        msg = "email_invalid" if e.response.status_code == 400 else f"tb_{e.response.status_code}"
        return RedirectResponse(f"{ROOT_PATH}/accounts/{uid}/edit?error={msg}", status_code=303)

    droit = (form.get("droit_acces") or "lecture").strip()
    if droit not in {r[0] for r in ROLES}:
        droit = "lecture"
    is_tenant_admin = u.get("authority") == "TENANT_ADMIN"
    # Admin (rôle ou TENANT_ADMIN) → pas de filtre chaufferies (voit tout, y
    # compris les chaufferies ajoutées plus tard).
    if droit == "admin" or is_tenant_admin:
        chaufferies: list[str] = []
    else:
        chaufferies = form.getlist("chaufferies") if hasattr(form, "getlist") else [
            v for k, v in form.multi_items() if k == "chaufferies"
        ]
    exp_raw = (form.get("expiration") or "").strip()
    expiration_ts = _parse_date_to_ms(exp_raw)

    attrs = {
        "societe": (form.get("societe") or "").strip(),
        "droit_acces": droit,
        "is_admin": droit == "admin",
        "access_rapport": form.get("access_rapport") == "on",
        "access_retroview": form.get("access_retroview") == "on",
        "access_spherys": form.get("access_spherys") == "on",
        # 'chaufferies' n'est plus ecrit ici : CanView (_sync_canview ci-dessous,
        # alimente par la variable locale `chaufferies`) est la seule source de verite.
    }
    if expiration_ts is not None:
        attrs["expiration_ts"] = expiration_ts
    elif exp_raw == "":
        # explicit clear
        attrs["expiration_ts"] = 0

    # Filtrage des mails : reserve aux comptes admin (les non-admins sont
    # deja filtres par CanView) ET conditionne a la sentinelle du gabarit.
    # Le role ne suffit pas : le bloc de cases n'est rendu que si `row.is_admin`
    # etait deja vrai a l'affichage, donc un POST qui PROMEUT un compte en
    # admin arrive sans aucun `mail_devices` — `followed` vide, tout le parc
    # exclu, compte muet a jamais et sans trace. La sentinelle distingue
    # "l'operateur a tout decoche" (intention) de "le formulaire ne portait pas
    # ce bloc" (artefact) : deux intentions opposees, meme POST sans elle.
    if (droit == "admin" or is_tenant_admin) and form.get("mail_devices_present"):
        followed = set(form.getlist("mail_devices") if hasattr(form, "getlist") else
                       [v for k, v in form.multi_items() if k == "mail_devices"])
        attrs[MAIL_EXCLUDE_ATTR] = [c["id"] for c in _list_chaufferies(tb)
                                    if c["id"] not in followed]

    tb.save_server_attrs("USER", uid, attrs)
    # Yahtec RBAC : reconcilier CanView (party-customer du user -> site-customers)
    fresh = tb.get_user(uid)
    pcid = (fresh.get("customerId") or {}).get("id")
    if fresh.get("authority") == "CUSTOMER_USER" and pcid and pcid != YAHTEC_CID:
        _sync_canview(tb, pcid, droit, chaufferies)
    return RedirectResponse(f"{ROOT_PATH}/accounts/{uid}/edit?saved=1", status_code=303)


@app.post("/accounts/{uid}/delete")
def account_delete(uid: str, user: dict = Depends(require_user)):
    tb = TBClient()
    # Gardes miroir de _set_account_active (I10) : la suppression est
    # definitive, elle doit refuser AU MOINS ce que la desactivation refuse.
    # Fail-closed : si on ne peut pas etablir que la cible est un CUSTOMER_USER
    # (introuvable ou authority indeterminee), on ne supprime pas.
    try:
        u = tb.get_user(uid)
    except requests.HTTPError:
        return RedirectResponse(f"{ROOT_PATH}/?error=not_found", status_code=303)
    authority = u.get("authority")
    if authority == "TENANT_ADMIN":
        # Jamais supprimer un tenant-admin (je@/af@, ADMIN_OPS ou svc-tbnotify,
        # le compte sous lequel l'app tourne).
        return RedirectResponse(f"{ROOT_PATH}/?error=admin_no_delete", status_code=303)
    if authority != "CUSTOMER_USER":
        # Fail-closed : autorite inconnue -> on refuse la suppression.
        return RedirectResponse(f"{ROOT_PATH}/?error=delete_forbidden", status_code=303)
    current_email = user.get("u")
    if current_email and (u.get("email") or "").lower() == current_email.lower():
        return RedirectResponse(f"{ROOT_PATH}/?error=cannot_delete_self", status_code=303)
    try:
        tb.delete_user(uid)
    except requests.HTTPError as e:
        return RedirectResponse(f"{ROOT_PATH}/?error=delete_failed_{e.response.status_code}", status_code=303)
    return RedirectResponse(f"{ROOT_PATH}/?deleted=1", status_code=303)


def _set_account_active(uid: str, active: bool, current_email: str | None = None):
    tb = TBClient()
    try:
        u = tb.get_user(uid)
    except requests.HTTPError:
        return RedirectResponse(f"{ROOT_PATH}/?error=not_found", status_code=303)
    # Garde-fou : jamais desactiver un tenant-admin (dev je@/af@ ou ADMIN_OPS).
    if u.get("authority") == "TENANT_ADMIN":
        return RedirectResponse(f"{ROOT_PATH}/accounts/{uid}/edit?error=admin_no_deactivate", status_code=303)
    # Garde-fou : ne pas se desactiver soi-meme (auto-verrouillage).
    if not active and current_email and (u.get("email") or "").lower() == current_email.lower():
        return RedirectResponse(f"{ROOT_PATH}/accounts/{uid}/edit?error=cannot_deactivate_self", status_code=303)
    tb.set_credentials_enabled(uid, active)
    attrs = {"deactivated": not active}
    if active:
        # Reactivation : purger aussi expiration_ts. Sans ca, le cron nocturne
        # (cleanup_expired) re-desactive le compte la nuit suivante car
        # expiration_ts reste echu. 0 = "aucune expiration" (meme convention
        # que account_edit_save quand le champ date est vide, et que
        # cleanup_expired qui ignore exp in (None, "", 0)).
        attrs["expiration_ts"] = 0
    tb.save_server_attrs("USER", uid, attrs)
    return RedirectResponse(f"{ROOT_PATH}/accounts/{uid}/edit?saved=1", status_code=303)


@app.post("/accounts/{uid}/deactivate")
def account_deactivate(uid: str, user: dict = Depends(require_user)):
    return _set_account_active(uid, False, user.get("u"))


@app.post("/accounts/{uid}/reactivate")
def account_reactivate(uid: str, user: dict = Depends(require_user)):
    return _set_account_active(uid, True, user.get("u"))


# ─── Invitations ────────────────────────────────────────────────────────────

def _parse_date_to_ms(s: str) -> int | None:
    if not s:
        return None
    try:
        # date input renvoie "YYYY-MM-DD"
        tm = time.strptime(s, "%Y-%m-%d")
        return int(time.mktime(tm) * 1000)
    except ValueError:
        return None


@app.get("/invite", response_class=HTMLResponse)
def invite_get(request: Request, user: dict = Depends(require_user)):
    tb = TBClient()
    return templates.TemplateResponse("invite.html", {
        "request": request, "user": user, "root": ROOT_PATH,
        "chaufferies": _list_chaufferies(tb), "roles": ROLES,
    })


@app.get("/invite-temp", response_class=HTMLResponse)
def invite_temp_get(request: Request, error: str | None = None,
                    user: dict = Depends(require_user)):
    tb = TBClient()
    return templates.TemplateResponse("invite_temp.html", {
        "request": request, "user": user, "root": ROOT_PATH,
        "chaufferies": _list_chaufferies(tb), "roles": ROLES, "error": error,
    })


def _parse_invitees(form) -> list[dict]:
    """Champs invitee_<i>_first_name / _last_name / _email / _societe."""
    by_i: dict[int, dict] = {}
    items = form.multi_items() if hasattr(form, "multi_items") else list(form.items())
    for k, v in items:
        if not k.startswith("invitee_"):
            continue
        try:
            _, idx, field = k.split("_", 2)
        except ValueError:
            continue
        try:
            i = int(idx)
        except ValueError:
            continue
        by_i.setdefault(i, {})[field] = (v or "").strip()
    out = []
    for i in sorted(by_i):
        r = by_i[i]
        if not r.get("email"):
            continue
        out.append({
            "first_name": r.get("first_name", ""),
            "last_name": r.get("last_name", ""),
            "email": r["email"],
            "societe": r.get("societe", ""),
        })
    return out


def _send_invitation(tb: TBClient, invitee: dict, attrs: dict) -> tuple[bool, str]:
    """Crée l'utilisateur TB, génère un lien d'activation, envoie l'email."""
    party_cid = tb.ensure_party_customer(invitee["email"])
    payload = {
        "email": invitee["email"],
        "firstName": invitee["first_name"] or None,
        "lastName": invitee["last_name"] or None,
        "authority": "CUSTOMER_USER",
        "additionalInfo": dict(KIOSK_ADDITIONAL_INFO, portfolioRole="PARTY"),
        "customerId": {"entityType": "CUSTOMER", "id": party_cid},
    }
    try:
        created = tb.create_user(payload, send_activation_mail=False)
    except requests.HTTPError as e:
        msg = "déjà existant" if e.response.status_code == 400 else f"erreur TB {e.response.status_code}"
        return False, msg
    uid = created["id"]["id"]
    # 'chaufferies' n'est plus ecrit comme attribut USER : CanView (_sync_canview
    # ci-dessous) est la seule source de verite. On la retire donc de full_attrs
    # (le dict persiste), mais on garde `attrs` intact pour l'appel _sync_canview
    # qui a besoin de attrs["chaufferies"].
    full_attrs = {k: v for k, v in attrs.items() if k != "chaufferies"}
    if invitee.get("societe"):
        full_attrs["societe"] = invitee["societe"]
    # I9 : ne PAS avaler ces echecs. Un compte cree sans attributs ni CanView
    # ne voit rien / ne recoit rien ; pire, sur un customer "Party — email"
    # orphelin reutilise, un CanView non reconcilie laisse le scope du
    # precedent titulaire. On remonte l'echec AVANT d'envoyer un mail qui
    # annoncerait (a tort) un acces fonctionnel.
    try:
        tb.save_server_attrs("USER", uid, full_attrs)
    except requests.HTTPError as e:
        return False, f"attributs non enregistrés ({e.response.status_code})"
    try:
        _sync_canview(tb, party_cid, attrs.get("droit_acces", "lecture"), attrs.get("chaufferies", []))
    except requests.HTTPError as e:
        return False, f"CanView non synchronisé ({e.response.status_code})"
    try:
        link = tb.activation_link(uid)
    except requests.HTTPError as e:
        return False, f"lien activation indisponible ({e.response.status_code})"
    # Réécrit l'URL pour pointer sur le host public
    if TB_PUBLIC_URL and link.startswith(("http://", "https://")):
        idx = link.find("/", len("https://"))
        if idx > 0:
            link = TB_PUBLIC_URL + link[idx:]
    html = _invite_email_html(invitee, link, attrs)
    text = _invite_email_text(invitee, link)
    try:
        send_mail([invitee["email"]], "Votre accès TDUO", html, text=text)
    except Exception as e:  # noqa: BLE001
        return False, f"mail KO ({e})"
    return True, "ok"


def _invite_email_html(invitee: dict, link: str, attrs: dict) -> str:
    nom = (invitee.get("first_name") or "") + " " + (invitee.get("last_name") or "")
    nom = nom.strip() or invitee["email"]
    exp_ts = attrs.get("expiration_ts")
    exp_line = ""
    if exp_ts:
        exp_line = f"<p style='color:#555'>Votre compte expirera le <b>{time.strftime('%d/%m/%Y', time.localtime(exp_ts/1000))}</b>.</p>"
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222">
<p>Bonjour {nom},</p>
<p>Un compte vous a été créé sur la plateforme de supervision TDUO.</p>
<p>Pour l'activer et choisir votre mot de passe, cliquez sur le lien ci-dessous&nbsp;:</p>
<p><a href="{link}" style="display:inline-block;background:#1976d2;color:#fff;padding:10px 18px;border-radius:5px;text-decoration:none">Activer mon compte</a></p>
<p style="font-size:12px;color:#888">Ou copiez-collez ce lien : {link}</p>
{exp_line}
<p>Cordialement,<br>L'équipe TDUO</p>
</body></html>"""


def _invite_email_text(invitee: dict, link: str) -> str:
    nom = (invitee.get("first_name") or "") + " " + (invitee.get("last_name") or "")
    nom = nom.strip() or invitee["email"]
    return (f"Bonjour {nom},\n\n"
            f"Un compte TDUO vous a été créé. Activez-le ici :\n{link}\n\n"
            f"L'équipe TDUO")


def _common_invite_attrs(form) -> dict:
    droit = (form.get("droit_acces") or "lecture").strip()
    if droit not in {r[0] for r in ROLES}:
        droit = "lecture"
    # Admin → pas de filtre chaufferies (voit tout y compris les futures).
    if droit == "admin":
        chaufferies: list[str] = []
    else:
        chaufferies = form.getlist("chaufferies") if hasattr(form, "getlist") else [
            v for k, v in form.multi_items() if k == "chaufferies"
        ]
    return {
        "droit_acces": droit,
        "is_admin": droit == "admin",
        "access_rapport": form.get("access_rapport") == "on",
        "access_retroview": form.get("access_retroview") == "on",
        "access_spherys": form.get("access_spherys") == "on",
        "chaufferies": chaufferies,
    }


@app.post("/invite")
async def invite_post(request: Request, user: dict = Depends(require_user)):
    form = await request.form()
    invitees = _parse_invitees(form)
    if not invitees:
        return RedirectResponse(f"{ROOT_PATH}/invite?error=no_email", status_code=303)
    attrs = _common_invite_attrs(form)
    tb = TBClient()
    ok = 0
    fails: list[str] = []
    for inv in invitees:
        success, msg = _send_invitation(tb, inv, attrs)
        if success:
            ok += 1
        else:
            fails.append(f"{inv['email']}: {msg}")
    if fails:
        return RedirectResponse(
            f"{ROOT_PATH}/?invited={ok}&error=" + ",".join(fails)[:300], status_code=303)
    return RedirectResponse(f"{ROOT_PATH}/?invited={ok}", status_code=303)


@app.post("/invite-temp")
async def invite_temp_post(request: Request, user: dict = Depends(require_user)):
    form = await request.form()
    email = (form.get("email") or "").strip()
    if not email:
        return RedirectResponse(f"{ROOT_PATH}/invite-temp?error=no_email", status_code=303)
    invitee = {
        "first_name": (form.get("first_name") or "").strip(),
        "last_name": (form.get("last_name") or "").strip(),
        "email": email,
        "societe": (form.get("societe") or "").strip(),
    }
    attrs = _common_invite_attrs(form)
    # M16 : une date d'expiration absente ou impossible à parser ne doit JAMAIS
    # créer un compte permanent en silence — c'est une invitation *temporaire*.
    exp_ts = _parse_date_to_ms((form.get("expiration") or "").strip())
    if not exp_ts:
        return RedirectResponse(f"{ROOT_PATH}/invite-temp?error=bad_expiration", status_code=303)
    attrs["expiration_ts"] = exp_ts
    tb = TBClient()
    ok, msg = _send_invitation(tb, invitee, attrs)
    if ok:
        return RedirectResponse(f"{ROOT_PATH}/?invited=1", status_code=303)
    return RedirectResponse(f"{ROOT_PATH}/invite-temp?error={msg}", status_code=303)


if __name__ == "__main__":
    import uvicorn
    host, port = os.environ.get("WEB_BIND", "127.0.0.1:8765").split(":")
    uvicorn.run("webapp:app", host=host, port=int(port), proxy_headers=True, forwarded_allow_ips="*")

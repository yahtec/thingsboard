"""Shared helpers for tb-notify (TB API client, SMTP, evt_* pairing)."""
from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("tb_notify.common")

LOG_DIR = Path(os.environ.get("TBN_LOG_DIR", "/var/log"))
JWT_CACHE = Path("/tmp/tb-notify-jwt.json")

# Profil devices + customer racine Yahtec (derivation CanView -> chaufferies).
# TB_DEVICE_PROFILE_NAME est le meme env var que webapp.py -> valeurs coherentes.
PROFILE = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
YAHTEC_CID = "2e521d10-3e5d-11f1-bbfe-e1395562cba0"
KIOSK_DASH = "0964da30-3e56-11f1-bbfe-e1395562cba0"

# evt_* dictionaries — kept in sync with widgets/events-history.controller.js.
FAULT_LABELS = {0:'',1:'Defaut sonde depart',2:'Defaut sonde retour',3:'Defaut sonde fumee',4:'Defaut sonde pression',5:'Defaut debit eau',6:'Defaut surpression eau',7:'Surchauffe',8:'Defaut bruleur',9:'Defaut ventil. bruleur',10:'Defaut preventilation',11:'Defaut delta temp.',12:'Defaut temp. fumee',13:'Defaut circuit fumee',14:'Bruleur non linearise',15:'Defaut communication',16:'Defaut sous-tension',17:'Defaut surtension',18:'Manque phase',19:'Marche a sec',20:'Pression trop forte',21:'Pression trop faible',22:'Moteur trop chaud',23:'Defaut moteur',24:'Pompe bloquee',25:'Surchauffe module',26:'Avertissement module',27:'Defaut module',28:'Defaut capteur',29:'Defaut communication',30:'Defaut vanne eau',31:'Utilisation excessive',32:'Adaptation plage',33:'Surcharge mecanique',34:'Defaut securite',35:'Erreur test clapet',36:'Temperature trop elevee',37:'Fumee detectee',38:'Defaut communication',39:'Defaut communication',40:'Defaut communication',41:'Pression trop faible',42:'Redemarrage regulateur',43:'Manipulation tactile',44:'Filtre encrasse',45:'Defaut carte 1',46:'Defaut carte 2',47:'Defaut carte 3',48:'Defaut carte 4',49:'Defaut carte 5',50:'Defaut carte 6',51:'Defaut carte 7',52:'Defaut bruleur 8',53:'Defaut bruleur 9',54:'Defaut bruleur 10',55:'Defaut bruleur 11',56:'Defaut bruleur 12',57:'Defaut bruleur 13',58:'Defaut interne boitier',59:'Defaut general boitier',60:'Nb max reset atteint',61:'Defaut pompe ECS',62:'Defaut module FTP',63:'Defaut pression fumee',70:'Defaut sonde T entree chaud.',71:'Defaut sonde T sortie chaud.',72:'Defaut sonde T fumee chaud.',73:'Defaut sonde T entree PAC',74:'Defaut sonde T BP',75:'Defaut sonde T HP-h',76:'Defaut sonde T HP-c',77:'Defaut sonde T air ext.',78:'Defaut pression air',79:'Defaut pression eau',80:'Defaut pression HP',81:'Defaut pression BP',82:'Gaz detecte',83:'Defaut surchauffe chaud.',84:'Defaut com. pompe',85:'Defaut com. compresseur',86:'Defaut com. gaz G20',87:'Defaut com. gaz R290',88:'Defaut communication',89:'Defaut pression eau',90:'Defaut HP max',91:'Defaut BP min',92:'Defaut variateur 0Hz',93:'Defaut variateur',94:'Defaut surchauffe PAC',95:'Defaut T sortie PAC',96:'Defaut T entree PAC',97:'Defaut T BP',98:'Defaut T HP chaud',99:'Defaut T HP froid',100:'Defaut pression eau bas',101:'Defaut pression eau haut',102:'Defaut pression air',103:'Defaut vitesse ventilateur',104:'Defaut sonde T entree module',105:'Defaut sonde T exterieure',106:'Defaut sonde T sortie ECS',107:'Defaut sonde T entree ECS',108:'Defaut sonde T sortie chauffage',109:'Defaut sonde T entree chauffage',110:'Defaut sonde T stockage',111:'Gaz R290 détecté',112:'Gaz G20 détecté',113:'Defaut temperature sortie chaudiere'}

DEVICE_LABELS = {0:'',1:'Chaudiere 1',2:'Chaudiere 2',3:'Chaudiere 3',4:'Chaudiere 4',5:'Chaudiere 5',6:'Chaudiere 6',7:'Chaudiere 7',8:'Chaudiere 8',9:'Chaudiere 9',10:'Chaudiere 10',11:'Chaudiere 11',12:'Chaudiere 12',15:'Pompe 1',16:'Pompe 2',17:'Pompe 3',18:'Pompe 4',19:'Pompe 5',20:'Calorimetre 1',21:'Calorimetre 2',22:'Calorimetre 3',23:'Calorimetre 4',24:'Calorimetre 5',25:'Circuit 1',26:'Circuit 2',27:'Circuit 3',28:'Circuit 4',29:'Circuit 5',30:'ECS 1',31:'ECS 2',32:'Entrees/Sorties',33:'Pompe filtre',34:'Remplisseur',35:'Module filtre',36:'Pompe 6',37:'Calorimetre 6',38:'Circuit 6',50:'PAC Hybride 1',51:'PAC Hybride 2',52:'PAC Hybride 3',53:'PAC Hybride 4',54:'PAC Hybride 5',55:'PAC Hybride 6',60:'Module',61:'Pompe 1 module',62:'Pompe 2 module',63:'Calorimetre module',64:'Chauffage',65:'Calorimetre chauffage',66:'ECS',67:'Pompe primaire ECS',68:'Pompe secondaire ECS'}

TYPE_LABELS = {0:'Information',1:'Panne',2:'Depannage',3:'Maintenance',4:'Resolue'}

EVT_KEYS = ['evt_type','evt_fault','evt_device','evt_status','evt_date','evt_time','evt_id','fault_src']
DEDUP_MS = 12000
PAIR_WIN_MS = 30000


def label_fault(code: int) -> str:
    return FAULT_LABELS.get(code) or f"Code {code}"


def label_device(code: int) -> str:
    if code == 0:
        return ""
    return DEVICE_LABELS.get(code) or f"Code {code}"


# ─── logging ────────────────────────────────────────────────────────────────

def setup_logging(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / "tb-notify.log")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    return log


# ─── ThingsBoard API client ─────────────────────────────────────────────────

class TBClient:
    def __init__(self, url: str | None = None, user: str | None = None, password: str | None = None):
        self.url = (url or os.environ["TB_URL"]).rstrip("/")
        self.user = user or os.environ["TB_USER"]
        self.password = password or os.environ["TB_PASS"]
        self.s = requests.Session()
        self._token: str | None = None
        self._token_exp: float = 0

    def _auth(self, force: bool = False):
        """force=True : re-authentifie inconditionnellement (saute le cache
        memoire ET le cache disque). Utilise par le retry 401 (I5) : sans ca,
        _auth() reposait sur le cache disque `/tmp/tb-notify-jwt.json` qui
        contient le MEME token invalide (son exp locale, inventee a
        l'ecriture = now+3600, n'a pas expire cote client bien qu'il soit
        deja mort cote serveur) -> tous les crons echouaient jusqu'a 1h apres
        une rotation de mdp / restart TB / logout-all."""
        if not force and self._token and time.time() < self._token_exp - 60:
            return
        if not force and JWT_CACHE.exists():
            try:
                d = json.loads(JWT_CACHE.read_text())
                if d.get("user") == self.user and d.get("exp", 0) > time.time() + 60:
                    self._token = d["token"]
                    self._token_exp = d["exp"]
                    self.s.headers["X-Authorization"] = f"Bearer {self._token}"
                    return
            except Exception:
                pass
        r = self.s.post(f"{self.url}/api/auth/login",
                        json={"username": self.user, "password": self.password}, timeout=15)
        r.raise_for_status()
        self._token = r.json()["token"]
        self._token_exp = time.time() + 3600
        self.s.headers["X-Authorization"] = f"Bearer {self._token}"
        try:
            JWT_CACHE.write_text(json.dumps({"user": self.user, "token": self._token, "exp": self._token_exp}))
            os.chmod(JWT_CACHE, 0o600)
        except Exception:
            pass

    def _invalidate_cached_token(self) -> None:
        """401 recu : le token en memoire ET le cache disque sont morts.
        Invalider les deux avant de re-authentifier (voir _auth(force=True))."""
        self._token = None
        try:
            JWT_CACHE.unlink(missing_ok=True)
        except Exception:
            pass

    def _req(self, method: str, path: str, **kw) -> requests.Response:
        self._auth()
        r = self.s.request(method, f"{self.url}{path}", timeout=30, **kw)
        if r.status_code == 401:
            self._invalidate_cached_token()
            self._auth(force=True)
            r = self.s.request(method, f"{self.url}{path}", timeout=30, **kw)
        r.raise_for_status()
        return r

    def get(self, path: str, **kw): return self._req("GET", path, **kw).json()

    def post_json(self, path: str, body: Any) -> Any:
        r = self._req("POST", path, json=body)
        if r.text:
            try:
                return r.json()
            except ValueError:
                return None
        return None

    def delete(self, path: str) -> None:
        # Reutilise _req -> beneficie du meme fix 401 (I5) sans dupliquer la logique.
        self._req("DELETE", path)

    def list_devices_by_profile(self, profile_name: str) -> list[dict]:
        out, page = [], 0
        while True:
            d = self.get(f"/api/tenant/devices?pageSize=200&page={page}")
            for dev in d.get("data", []):
                if dev.get("type") == profile_name:
                    out.append(dev)
            if not d.get("hasNext"):
                break
            page += 1
        return out

    def get_server_attrs(self, etype: str, eid: str, keys: Iterable[str] | None = None) -> dict:
        path = f"/api/plugins/telemetry/{etype}/{eid}/values/attributes/SERVER_SCOPE"
        if keys:
            path += "?keys=" + ",".join(keys)
        return {a["key"]: a["value"] for a in self.get(path)}

    def save_server_attrs(self, etype: str, eid: str, kv: dict) -> None:
        self.post_json(f"/api/plugins/telemetry/{etype}/{eid}/SERVER_SCOPE", kv)

    # ── Customers / relations RBAC (grant/revoke CanView) ───────────────
    def ensure_customer_by_title(self, title: str) -> str:
        page = self.get(f"/api/customers?pageSize=200&page=0&textSearch={requests.utils.quote(title)}")
        for c in page.get("data", []):
            if c.get("title") == title:
                return c["id"]["id"]
        return self.post_json("/api/customer", {"title": title})["id"]["id"]

    def customer_has_dashboard(self, customer_id: str, dashboard_id: str) -> bool:
        d = self.get(f"/api/customer/{customer_id}/dashboards?pageSize=200&page=0")
        return any((x.get("id") or {}).get("id") == dashboard_id for x in d.get("data", []))

    def assign_dashboard_to_customer(self, customer_id: str, dashboard_id: str) -> None:
        """Idempotent : no-op si déjà assigné."""
        if not self.customer_has_dashboard(customer_id, dashboard_id):
            self.post_json(f"/api/customer/{customer_id}/dashboard/{dashboard_id}", {})

    def ensure_party_customer(self, email: str) -> str:
        cid = self.ensure_customer_by_title(f"Party — {email}")
        # Chantier #5 (B) : garantir l'accès au dashboard "Mes Installations".
        self.assign_dashboard_to_customer(cid, KIOSK_DASH)
        return cid

    def list_canview(self, from_cid: str) -> list[str]:
        rels = self.get(f"/api/relations?fromId={from_cid}&fromType=CUSTOMER")
        return [r["to"]["id"] for r in rels
                if r.get("type") == "CanView" and r.get("typeGroup") == "COMMON"]

    def canview_site_ids(self, party_cid):
        """Set des site-customer ids qu'un party-customer peut voir (relations CanView)."""
        return set(self.list_canview(party_cid))

    def create_relation(self, from_cid: str, to_cid: str) -> None:
        self.post_json("/api/relation", {
            "from": {"id": from_cid, "entityType": "CUSTOMER"},
            "to": {"id": to_cid, "entityType": "CUSTOMER"},
            "type": "CanView", "typeGroup": "COMMON"})

    def delete_relation(self, from_cid: str, to_cid: str) -> None:
        self.delete(f"/api/relation?fromId={from_cid}&fromType=CUSTOMER"
                    f"&relationType=CanView&relationTypeGroup=COMMON"
                    f"&toId={to_cid}&toType=CUSTOMER")

    def reconcile_canview(self, party_cid: str, desired_site_ids, fleet_site_ids) -> None:
        existing = set(self.list_canview(party_cid))
        desired = set(desired_site_ids)
        for sid in desired - existing:
            self.create_relation(party_cid, sid)
        for sid in (existing & set(fleet_site_ids)) - desired:
            self.delete_relation(party_cid, sid)

    # ── Users ───────────────────────────────────────────────────────────
    def list_users(self) -> list[dict]:
        """Tous les users visibles par TENANT_ADMIN (admins tenant + customer users)."""
        out, page = [], 0
        while True:
            d = self.get(f"/api/users?pageSize=200&page={page}")
            out.extend(d.get("data", []))
            if not d.get("hasNext"):
                break
            page += 1
        return out

    def list_customer_users(self, customer_id: str) -> list[dict]:
        out, page = [], 0
        while True:
            d = self.get(f"/api/customer/{customer_id}/users?pageSize=200&page={page}")
            out.extend(d.get("data", []))
            if not d.get("hasNext"):
                break
            page += 1
        return out

    def list_all_users(self, customer_id: str | None = None) -> list[dict]:
        # /api/users couvre déjà tenant admins + customer users du tenant.
        return self.list_users()

    def get_user(self, user_id: str) -> dict:
        return self.get(f"/api/user/{user_id}")

    def create_user(self, user: dict, send_activation_mail: bool = False) -> dict:
        path = f"/api/user?sendActivationMail={'true' if send_activation_mail else 'false'}"
        return self.post_json(path, user)

    def update_user(self, user: dict) -> dict:
        return self.post_json("/api/user", user)

    def delete_user(self, user_id: str) -> None:
        self.delete(f"/api/user/{user_id}")

    def set_credentials_enabled(self, user_id: str, enabled: bool) -> None:
        """Bloque (False) / debloque (True) la connexion TB de l'utilisateur.
        userCredentialsEnabled=false invalide aussi les sessions cote TB."""
        val = "true" if enabled else "false"
        self.post_json(f"/api/user/{user_id}/userCredentialsEnabled?userCredentialsEnabled={val}", None)

    def activation_link(self, user_id: str) -> str:
        # B : meme robustesse 401 que _req (I5). GET direct (pas via _req car on
        # veut le texte brut), donc on duplique le retry : sur 401, invalider le
        # token cache (memoire + disque) et re-authentifier de force avant de
        # rejouer une fois — sinon une invitation echoue apres rotation mdp /
        # restart TB tant que le JWT mort du cache disque n'a pas "expire".
        url = f"{self.url}/api/user/{user_id}/activationLink"
        self._auth()
        r = self.s.get(url, timeout=30)
        if r.status_code == 401:
            self._invalidate_cached_token()
            self._auth(force=True)
            r = self.s.get(url, timeout=30)
        r.raise_for_status()
        body = r.text.strip()
        if body.startswith("{") or body.startswith('"'):
            try:
                j = json.loads(body)
                if isinstance(j, str):
                    return j
                if isinstance(j, dict):
                    for k in ("value", "activationLink", "link"):
                        if k in j:
                            return str(j[k])
            except ValueError:
                pass
        return body.strip('"')

    # ── Email recipients (calculés depuis les comptes user) ─────────────
    def site_of_devices(self, profile_name: str) -> dict:
        """Map {device_id: site_customer_id} pour les devices du profil ayant un
        site_customer_id. Base commune de la derivation CanView -> device-ids
        (pre-cochage tb-notify webapp + routage des mails ci-dessous) : calculee
        une fois, puis intersectee avec les CanView de chaque party-customer."""
        out = {}
        for d in self.list_devices_by_profile(profile_name):
            scid = self.get_server_attrs("DEVICE", d["id"]["id"], ["site_customer_id"]).get("site_customer_id")
            if scid:
                out[d["id"]["id"]] = scid
        return out

    def _collect_user_attrs(self) -> list[dict]:
        """Pour chaque user : son is_admin + email/authority + la liste des
        device-ids qu'il peut voir, DERIVEE DE CanView (l'attribut USER
        `chaufferies` n'est plus ecrit ni lu — CanView est la seule source de
        verite). Shape identique (liste de device-id str) : get_recipients_for_device
        et get_admin_emails restent inchanges.
        Renvoie liste de dicts utilisables par get_recipients_for_device / get_admin_emails."""
        site_of_dev = self.site_of_devices(PROFILE)  # {device_id: site_customer_id}, calcule 1 fois
        out = []
        for u in self.list_users():
            uid = u["id"]["id"]
            email = (u.get("email") or "").strip()
            if not email:
                continue
            # Chantier #5 (A1) : NE PAS skipper sur additionalInfo.userCredentialsEnabled.
            # TB le pose false à la création d'un compte non-activé et ne le corrige qu'au
            # 1er login -> un intervenant activé mais jamais connecté était exclu à tort du
            # routage. Le routage repose désormais sur la seule vérité RBAC (CanView + is_admin).
            try:
                attrs = self.get_server_attrs(
                    "USER", uid, ["is_admin", "deactivated", MAIL_EXCLUDE_ATTR])
            except Exception:
                # I6 : fail-closed, pas fail-open. `attrs = {}` traiterait un
                # `deactivated` comme actif (re-routage) et un `is_admin` comme
                # non-admin (spam per-device) juste parce que le fetch a echoue.
                # On saute cet utilisateur pour CE run (au pire il manque un
                # destinataire une fois ; au prochain run le fetch reussira).
                logger.warning("skip user %s (%s): attrs fetch failed", uid, email, exc_info=True)
                continue
            if attrs.get("deactivated"):
                continue  # compte desactive (tb-notify) -> pas de mail de defaut
            # chaufferies = device-ids visibles via CanView du party-customer dedie.
            # Tenant-admin / customer-user rattache a yahtec -> [] (ils passent par
            # get_admin_emails, pas par le routage par-device).
            party_cid = (u.get("customerId") or {}).get("id")
            if u.get("authority") == "CUSTOMER_USER" and party_cid and party_cid != YAHTEC_CID:
                site_ids = self.canview_site_ids(party_cid)
                chauff = [dev_id for dev_id, sc in site_of_dev.items() if sc in site_ids]
            else:
                chauff = []
            out.append({
                "id": uid,
                "email": email,
                "authority": u.get("authority"),
                "is_admin": bool(attrs.get("is_admin")),
                "chaufferies": [str(x) for x in chauff],
                "mail_exclude": load_exclude_list(attrs.get(MAIL_EXCLUDE_ATTR)),
            })
        return out

    def get_recipients_for_device(self, device_id: str,
                                  users: list[dict] | None = None) -> list[str]:
        """Emails des gestionnaires de cette chaufferie pour les mails
        d'**apparition de défaut**.

        - CUSTOMER_USER **non-admin** ayant `device_id` dans son attribut
          `chaufferies` → inclus.
        - TENANT_ADMIN et CUSTOMER_USER+is_admin → **EXCLUS** : ils passent par
          le recap admin de `fault_digest.py`, dont les destinataires et la
          cadence viennent de `get_admin_targets()` (au plus 2 mails/jour).
        """
        if users is None:
            users = self._collect_user_attrs()
        out: list[str] = []
        for u in users:
            if u["authority"] != "CUSTOMER_USER":
                continue
            if u["is_admin"]:
                continue
            if device_id in u["chaufferies"]:
                out.append(u["email"])
        seen = set()
        return [e for e in out if not (e in seen or seen.add(e))]

    def get_admin_emails(self, users: list[dict] | None = None) -> list[str]:
        """Emails des TENANT_ADMIN + CUSTOMER_USER avec is_admin=true.
        Exclut le compte de service lui-meme (M14) : svc-tbnotify@ est
        TENANT_ADMIN mais ne doit pas se spammer / apparaitre dans le digest."""
        if users is None:
            users = self._collect_user_attrs()
        self_email = (self.user or "").strip().lower()
        out = [u["email"] for u in users
               if (u["authority"] == "TENANT_ADMIN" or u["is_admin"])
               and u["email"].strip().lower() != self_email]
        seen = set()
        return [e for e in out if not (e in seen or seen.add(e))]

    def get_admin_targets(self, users: list[dict] | None = None) -> list[dict]:
        """Destinataires du recap avec ce qu'il faut pour evaluer leur cadence :
        leur id (porteur de l'attribut d'etat) et leurs exclusions. Meme filtre
        que get_admin_emails, compte de service EXCLU (M14) : svc-tbnotify@ est
        TENANT_ADMIN mais ne doit pas se spammer."""
        if users is None:
            users = self._collect_user_attrs()
        self_email = (self.user or "").strip().lower()
        out: list[dict] = []
        seen: set[str] = set()
        for u in users:
            if not (u["authority"] == "TENANT_ADMIN" or u["is_admin"]):
                continue
            email = u["email"]
            low = email.strip().lower()
            if low == self_email or low in seen:
                continue
            seen.add(low)
            out.append({"id": u["id"], "email": email,
                        "exclude": set(u.get("mail_exclude") or ())})
        return out

    def get_digest_state(self, user_id: str) -> dict[str, int]:
        attrs = self.get_server_attrs("USER", user_id, [DIGEST_STATE_ATTR])
        return load_digest_state(attrs.get(DIGEST_STATE_ATTR))

    def save_digest_state(self, user_id: str, state: dict[str, int]) -> None:
        self.save_server_attrs("USER", user_id, {DIGEST_STATE_ATTR: state})

    def get_timeseries(self, device_id: str, keys: Iterable[str], start_ts: int, end_ts: int,
                       limit: int = 50000) -> dict[str, list[dict]]:
        path = (f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                f"?keys={','.join(keys)}&startTs={start_ts}&endTs={end_ts}"
                f"&limit={limit}&agg=NONE&orderBy=ASC")
        return self.get(path)


# ─── evt_* pairing — mirrors widgets/events-history.controller.js ───────────

@dataclass
class Event:
    ts: int                  # raw TB ts (used for dedup)
    appear_ts: int | None
    type: int                # 1=apparition, 4=resolution
    fault: int
    device: int
    status: int
    fault_src: int
    evt_id: int
    date: str = ""
    time: str = ""
    resolved_ts: int | None = None
    resolved_date: str = ""
    resolved_time: str = ""


def collect_records(ts_payload: dict[str, list[dict]]) -> list[dict]:
    """Pivot {key: [{ts,value}]} → [{ts, evt_*: ...}], sorted by ts ASC."""
    by_ts: dict[int, dict] = {}
    for key, points in ts_payload.items():
        for p in points:
            ts = p["ts"]
            d = by_ts.setdefault(ts, {"ts": ts})
            d[key] = p["value"]
    return [by_ts[t] for t in sorted(by_ts)]


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def pair_events(records: list[dict]) -> list[Event]:
    """Pair appearance(1)/resolution(4), dedup retransmissions within 12s.
    Mirrors the dashboard widget so UI and notifications stay consistent."""
    events: list[Event] = []
    open_by_key: dict[str, Event] = {}
    last_ts_by_key: dict[str, int] = {}

    for r in records:
        try:
            typ = int(r["evt_type"])
        except (KeyError, ValueError, TypeError):
            continue
        fault = _to_int(r.get("evt_fault"))
        dev = _to_int(r.get("evt_device"))
        status = _to_int(r.get("evt_status"))
        fsrc_raw = r.get("fault_src")
        fsrc = -1 if fsrc_raw in (None, "") else _to_int(fsrc_raw, -1)
        rec = Event(
            ts=r["ts"], appear_ts=r["ts"], type=typ, fault=fault, device=dev,
            status=status, fault_src=fsrc, evt_id=_to_int(r.get("evt_id")),
            date=r.get("evt_date") or "", time=r.get("evt_time") or "",
        )
        if typ == 1:
            k = f"{fault}|{dev}"
            dk = f"{k}:1"
            if r["ts"] - last_ts_by_key.get(dk, 0) < DEDUP_MS:
                continue
            last_ts_by_key[dk] = r["ts"]
            open_by_key[k] = rec
            events.append(rec)
        elif typ == 4:
            k = f"{fault}|{dev}"
            dk = f"{k}:4"
            if r["ts"] - last_ts_by_key.get(dk, 0) < DEDUP_MS:
                continue
            last_ts_by_key[dk] = r["ts"]
            o = open_by_key.pop(k, None)
            if o is not None:
                o.resolved_ts = r["ts"]
                o.resolved_date = rec.date
                o.resolved_time = rec.time
                o.status = 0
            else:
                rec.resolved_ts = r["ts"]
                rec.resolved_date = rec.date
                rec.resolved_time = rec.time
                rec.appear_ts = None
                rec.date = ""
                rec.time = ""
                rec.status = 0
                events.append(rec)
        else:
            events.append(rec)

    # Reverse-pair late type=1 with standalone type=4 received first.
    standalones = [e for e in events if e.type == 4 and e.appear_ts is None]
    opens = [e for e in events if e.type == 1 and e.resolved_ts is None]
    for s in standalones:
        best, best_dt = None, PAIR_WIN_MS
        for o in opens:
            if o.fault != s.fault or o.device != s.device:
                continue
            dt = abs(o.appear_ts - s.resolved_ts)
            if dt < best_dt:
                best, best_dt = o, dt
        if best is None:
            continue
        a = min(s.resolved_ts, best.appear_ts)
        b = max(s.resolved_ts, best.appear_ts)
        best.appear_ts = a
        best.resolved_ts = b
        best.status = 0
        if a == s.resolved_ts:
            best.date, best.time = s.resolved_date, s.resolved_time
        if b == s.resolved_ts:
            best.resolved_date, best.resolved_time = s.resolved_date, s.resolved_time
        events.remove(s)

    return events


def open_faults(events: list[Event]) -> list[Event]:
    return [e for e in events if e.type == 1 and e.resolved_ts is None]


# ─── Attributs d'etat (memoires des crons) ─────────────────────────────────

def load_state_attr(raw) -> dict:
    """Parse la valeur d'un attribut SERVER_SCOPE servant de memoire a un cron.
    TB peut rendre l'objet JSON deja deserialise ou une chaine. Tout ce qui
    n'est pas un dict exploitable (absent, JSON invalide, mauvais type,
    contenu corrompu) vaut etat vierge : on repart de zero plutot que de faire
    tomber le cron (spec §5.3)."""
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def load_int_map(raw) -> dict[str, int]:
    """`load_state_attr` + coercion des valeurs en int. Une entree
    inexploitable est ignoree seule, sans invalider les autres."""
    out: dict[str, int] = {}
    for k, v in load_state_attr(raw).items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


# ─── Mute global d'une chaufferie ──────────────────────────────────────────
# Rend une chaufferie muette pour TOUS les mails, recap comme client. Par
# defaut le banc d'essai degrade 2610000001 (souvent sans carte PAC ni
# capteurs -> defauts non representatifs). Vide = n'exclut rien.

DEFAULT_EXCLUDE_DEVICES = "2610000001"


def excluded_device_names() -> set[str]:
    raw = os.environ.get("NOTIFY_EXCLUDE_DEVICES", DEFAULT_EXCLUDE_DEVICES)
    return {s.strip() for s in raw.split(",") if s.strip()}


def filter_excluded(devices: list[dict], excluded: set[str]) -> tuple[list[dict], list[str]]:
    """Retire les devices dont le `name` est dans `excluded`. Retourne
    (gardes, noms_retires) pour que l'appelant journalise ce qui a ete retire
    — jamais un drop silencieux."""
    kept: list[dict] = []
    dropped: list[str] = []
    for d in devices:
        if d.get("name") in excluded:
            dropped.append(d.get("name"))
        else:
            kept.append(d)
    return kept, dropped


# ─── Reglages de cadence (spec §8) ─────────────────────────────────────────
# Lus a chaque appel (pas au chargement du module) pour que les tests
# puissent les surcharger avec monkeypatch.setenv.

def _env_int(name: str, default: int) -> int:
    """Entier depuis l'environnement, avec repli silencieux sur le defaut :
    une variable mal saisie ne doit pas empecher un cron de tourner."""
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def mail_grace_ms() -> int:
    """Sursis entre l'apparition d'un defaut et le premier mail qui en parle.
    Un defaut resolu pendant son sursis ne produit aucun mail."""
    return _env_int("MAIL_GRACE_MIN", 60) * 60 * 1000


def digest_recap_hour() -> int:
    """Heure locale a laquelle le recap admin quotidien est du."""
    return _env_int("DIGEST_RECAP_HOUR", 7)


def digest_min_gap_ms() -> int:
    """Ecart minimal entre deux mails admin : supprime le quotidien s'il
    tombe juste apres un mail rapide."""
    return _env_int("DIGEST_MIN_GAP_HOURS", 6) * 3600 * 1000


def digest_fast_quota_ms() -> int:
    """Intervalle minimal entre deux mails rapides. C'est le limiteur
    anti-battement : une chaufferie qui bat de l'aile ne peut pas declencher
    un mail rapide par cycle."""
    return _env_int("DIGEST_FAST_QUOTA_HOURS", 24) * 3600 * 1000


REMINDER_STEPS_DEFAULT = (24, 72, 168)


def reminder_steps_ms() -> list[int]:
    """Paliers d'escalade des rappels client, en millisecondes. Une entree
    illisible est ignoree ; une liste vide retombe sur le defaut, sinon le
    moteur de rappel n'aurait plus aucun palier a appliquer."""
    raw = os.environ.get("NOTIFY_REMINDER_HOURS", "")
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part) * 3600 * 1000)
        except ValueError:
            continue
    return out or [h * 3600 * 1000 for h in REMINDER_STEPS_DEFAULT]


# ─── Etat de cadence du recap, porte par l'utilisateur (spec §5.1) ─────────

MAIL_EXCLUDE_ATTR = "mail_exclude_devices"
DIGEST_STATE_ATTR = "mail_digest_state"


def load_digest_state(raw) -> dict[str, int]:
    """Deux horodatages, toujours presents. `last_mail_ts` a 0 signifie
    "episode non encore annonce" ; `last_fast_ts` est un limiteur de debit
    qui survit a la fin d'un episode."""
    st = load_int_map(raw)
    return {"last_mail_ts": st.get("last_mail_ts", 0),
            "last_fast_ts": st.get("last_fast_ts", 0)}


def load_exclude_list(raw) -> list[str]:
    """Liste d'ids de devices depuis un attribut USER. Accepte une liste ou
    une chaine JSON ; tout le reste vaut liste vide (aucune exclusion), ce qui
    est le repli prudent pour un filtre de notification : un oubli de config
    produit un mail de trop, jamais un silence."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


# ─── SMTP ──────────────────────────────────────────────────────────────────

@dataclass
class MailConfig:
    host: str
    port: int
    user: str
    password: str
    from_addr: str
    from_name: str
    security: str  # "ssl" (TLS dès la connexion) ou "starttls"

    @classmethod
    def from_env(cls) -> "MailConfig":
        return cls(
            host=os.environ["SMTP_HOST"],
            port=int(os.environ.get("SMTP_PORT", 587)),
            user=os.environ["SMTP_USER"],
            password=os.environ["SMTP_PASS"],
            from_addr=os.environ["SMTP_FROM"],
            from_name=os.environ.get("SMTP_FROM_NAME", "TDUO Alertes"),
            security=os.environ.get("SMTP_SECURITY", "starttls").lower(),
        )


def send_mail(to: list[str], subject: str, html: str, text: str | None = None,
              cfg: MailConfig | None = None, retries: int = 3) -> None:
    cfg = cfg or MailConfig.from_env()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.from_name, cfg.from_addr))
    msg["To"] = ", ".join(to)
    msg.set_content(text or _html_to_text(html))
    msg.add_alternative(html, subtype="html")
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            ctx = ssl.create_default_context()
            if cfg.security == "ssl":
                smtp_cls = lambda: smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30, context=ctx)
            else:
                smtp_cls = lambda: smtplib.SMTP(cfg.host, cfg.port, timeout=30)
            with smtp_cls() as s:
                if cfg.security != "ssl":
                    s.starttls(context=ctx)
                s.login(cfg.user, cfg.password)
                s.send_message(msg)
            return
        except (smtplib.SMTPException, OSError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"SMTP send failed after {retries} attempts: {last_err}") from last_err


def _html_to_text(html: str) -> str:
    import re
    t = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()

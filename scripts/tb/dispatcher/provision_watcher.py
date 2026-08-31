#!/usr/bin/env python3
"""Provisioning watcher for unknown installations.

Reads `evt_unknown_id` events buffered on the gateway `heatPumpHybride`,
creates missing devices under the 'pac hybride' profile, and replays the
buffered telemetry payload onto the freshly-created device. Tracks progress
via the server-side attribute `last_provisioned_evt_ts` on the gateway.

Designed to run from cron every minute. Idempotent.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error


def _load_dotenv():
    """Charge TB_USER / TB_PASS depuis un .env (mode 600) place a cote de ce script.

    Les identifiants ne doivent JAMAIS revenir en dur ici : ce fichier est
    versionne dans un depot PUBLIC. Une variable d'environnement deja definie
    a la priorite sur le .env."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

TB_URL  = os.environ.get("TB_URL", "http://127.0.0.1:8080")
TB_USER = os.environ.get("TB_USER")
TB_PASS = os.environ.get("TB_PASS")
HUB_ID         = "2de23ab0-3e51-11f1-bbfe-e1395562cba0"
PAC_PROFILE_ID = "9de96d60-4225-11f1-bbfe-e1395562cba0"
YAHTEC_CUSTOMER_ID = "2e521d10-3e5d-11f1-bbfe-e1395562cba0"
INACTIVITY_MS  = 180000

LOG = lambda *a: print(time.strftime("[%Y-%m-%d %H:%M:%S]"), *a, flush=True)

def http(method, path, body=None, token=None, raw=False):
    url = TB_URL + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type":"application/json"}
    if token: headers["X-Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read().decode()
            if raw: return txt
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {body_txt}")

def login():
    res = http("POST","/api/auth/login",{"username":TB_USER,"password":TB_PASS})
    return res["token"]

def get_attr(token, key, default=0):
    res = http("GET", f"/api/plugins/telemetry/DEVICE/{HUB_ID}/values/attributes/SERVER_SCOPE?keys={key}", token=token)
    if not res: return default
    for kv in res:
        if kv.get("key") == key: return kv.get("value", default)
    return default

def set_attr(token, kv):
    http("POST", f"/api/plugins/telemetry/DEVICE/{HUB_ID}/SERVER_SCOPE", kv, token=token)

def list_devices_by_name(token):
    res = http("GET", "/api/tenant/devices?pageSize=1000&page=0", token=token)
    return {d["name"]: d for d in res["data"]}

def create_device(token, name):
    body = {
        "name": name,
        "label": f"Installation {name}",
        "deviceProfileId": {"entityType":"DEVICE_PROFILE","id":PAC_PROFILE_ID}
    }
    d = http("POST","/api/device", body, token=token)
    dev_id = d["id"]["id"]
    # Seed the per-installation metadata schema so the Unité dashboard's
    # ${latitude}, ${adresse}, ${entretien_*}, ${photo*} bindings have
    # something to read on day one. Values stay blank until edited via UI.
    seed = {
        "inactivityTimeout": INACTIVITY_MS,
        "nom_residence": "", "nom_alternatif": "",
        "adresse": "", "latitude": "", "longitude": "",
        "capacite": "", "type_logement": "",
        "entretien_nom": "", "entretien_numero": "", "entretien_rue": "",
        "entretien_cp": "", "entretien_ville": "", "entretien_logo": "",
        "photo": "", "photo_local": ""
    }
    http("POST", f"/api/plugins/telemetry/DEVICE/{dev_id}/SERVER_SCOPE",
         seed, token=token)
    # assign to yahtec customer so customer-level users can see it
    http("POST", f"/api/customer/{YAHTEC_CUSTOMER_ID}/device/{dev_id}", None, token=token)
    return dev_id

def fetch_unknown_events(token, start_ts):
    end_ts = int(time.time()*1000)
    url = (f"/api/plugins/telemetry/DEVICE/{HUB_ID}/values/timeseries"
           f"?keys=evt_unknown_id&startTs={start_ts+1}&endTs={end_ts}"
           f"&limit=10000&agg=NONE")
    res = http("GET", url, token=token) or {}
    return res.get("evt_unknown_id", [])

def replay(token, dev_id, ts, payload):
    """Inject the buffered telemetry payload into the new device at the original ts."""
    # /api/plugins/telemetry/{deviceId}/timeseries/ANY scope and timestamps
    body = [{"ts": int(ts), "values": payload}]
    http("POST", f"/api/plugins/telemetry/DEVICE/{dev_id}/timeseries/ANY",
         body, token=token, raw=True)

def main():
    if not TB_USER or not TB_PASS:
        sys.exit("TB_USER / TB_PASS absents : renseigner "
                 + os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    token = login()
    last_ts = int(get_attr(token, "last_provisioned_evt_ts", 0))
    LOG(f"watcher tick — last_provisioned_evt_ts={last_ts}")

    events = fetch_unknown_events(token, last_ts)
    if not events:
        LOG("no new unknown events")
        return

    LOG(f"{len(events)} unknown events to process")
    devices = list_devices_by_name(token)
    processed = 0
    new_max_ts = last_ts

    for ev in events:
        ts = int(ev["ts"]); val = ev["value"]
        try:
            data = json.loads(val) if isinstance(val, str) else val
            # strip() : un n de serie avec un retour-chariot ou un espace a cree
            # un device fantome le 2026-08-28 (cf. add-serial-trim.py). Le trim est
            # aussi pose en amont dans la rule chain ; ceci est la seconde ligne.
            inst_id = str(data.get("id")).strip()
            payload = data.get("payload") or {}
            if not inst_id or inst_id == "None":
                LOG(f"  skip ts={ts}: no id in event payload")
                new_max_ts = max(new_max_ts, ts)
                continue
            dev = devices.get(inst_id)
            if dev is None:
                LOG(f"  creating device {inst_id}")
                dev_id = create_device(token, inst_id)
                devices[inst_id] = {"id":{"id":dev_id},"name":inst_id}
                # log a provision event on the gateway
                http("POST", f"/api/plugins/telemetry/DEVICE/{HUB_ID}/timeseries/ANY",
                     [{"ts": int(time.time()*1000),
                       "values":{"evt_provision": json.dumps({"id":inst_id,"deviceId":dev_id})}}],
                     token=token, raw=True)
            else:
                dev_id = dev["id"]["id"]
            if payload:
                replay(token, dev_id, ts, payload)
            processed += 1
            new_max_ts = max(new_max_ts, ts)
        except Exception as e:
            LOG(f"  ERROR ts={ts}: {e}")
            # Don't advance cursor past failed events
            break

    if new_max_ts > last_ts:
        set_attr(token, {"last_provisioned_evt_ts": new_max_ts})
        LOG(f"advanced last_provisioned_evt_ts -> {new_max_ts} ({processed} processed)")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        LOG(f"FATAL: {e}")
        sys.exit(1)

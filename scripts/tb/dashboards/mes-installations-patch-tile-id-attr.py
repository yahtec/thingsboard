#!/usr/bin/env python3
"""
Patch HTML Value Card (entry tile) in dashboard "Mes Installations" :
bascule la datakey `id` de type 'timeseries' → 'attribute' (SERVER_SCOPE).

Idempotent : si la dataKey est déjà en attribute, ne refait rien.

Auth : TB_TOKEN, ou TB_USER + TB_PASS. Cible : TB_URL (defaut 127.0.0.1:8080).
"""
import json, os, sys, urllib.request, urllib.error

TB = os.environ.get("TB_URL", "http://127.0.0.1:8080")
DASHBOARD_ID = "0964da30-3e56-11f1-bbfe-e1395562cba0"

def req(method, url, headers=None, body=None):
    headers = headers or {}
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())

def auth_header():
    """En-tetes authentifies. Jeton via TB_TOKEN, sinon login TB_USER/TB_PASS.
    Aucun identifiant en dur : ce depot est public."""
    tok = os.environ.get("TB_TOKEN")
    if not tok:
        user, pwd = os.environ.get("TB_USER"), os.environ.get("TB_PASS")
        if not (user and pwd):
            sys.exit("Definir TB_TOKEN, ou TB_USER et TB_PASS.")
        tok = req("POST", f"{TB}/api/auth/login",
                  {"Content-Type": "application/json"},
                  {"username": user, "password": pwd})["token"]
    return {"Content-Type": "application/json", "X-Authorization": f"Bearer {tok}"}

# 1. Login
print("=== 1. Login ===")
hdr = auth_header()
print("Authenticated")

# 2. GET dashboard
print("\n=== 2. GET dashboard ===")
dash = req("GET", f"{TB}/api/dashboard/{DASHBOARD_ID}", hdr)
print(f"Dashboard '{dash['title']}' fetched ({len(dash['configuration']['widgets'])} widgets)")

# Backup
with open(f"/tmp/dashboard-{DASHBOARD_ID}-backup.json", "w") as f:
    json.dump(dash, f, indent=2)
print(f"Backup: /tmp/dashboard-{DASHBOARD_ID}-backup.json")

# 3. Locate the offending widget
widgets = dash["configuration"]["widgets"]
target_widget_id = None
target_widget = None

for wid, w in widgets.items():
    if w.get("typeFullFqn", "").endswith("html_value_card"):
        for ds in w.get("config", {}).get("datasources", []) or []:
            for dk in ds.get("dataKeys", []) or []:
                if dk.get("name") == "id" and dk.get("type") == "timeseries":
                    target_widget_id = wid
                    target_widget = w
                    break
        if target_widget_id:
            break

if not target_widget_id:
    print("\n✅ No HTML Value Card reads `id` as timeseries — already patched or nothing to do")
    sys.exit(0)

print(f"\n=== 3. Found target widget: id={target_widget_id} title='{target_widget.get('config', {}).get('title', '?')}' ===")

# 4. Patch the dataKey
patched = 0
for ds in target_widget["config"]["datasources"]:
    for dk in ds.get("dataKeys", []) or []:
        if dk.get("name") == "id" and dk.get("type") == "timeseries":
            print(f"  Before: name='{dk.get('name')}' type='{dk.get('type')}'")
            dk["type"] = "attribute"
            print(f"  After : name='{dk.get('name')}' type='{dk.get('type')}'")
            patched += 1

print(f"Patched {patched} dataKey(s)")

# 5. POST dashboard back
print("\n=== 4. POST patched dashboard ===")
try:
    resp = req("POST", f"{TB}/api/dashboard", hdr, dash)
    print(f"✅ POST success, version={resp.get('version', '?')}")
except urllib.error.HTTPError as e:
    print(f"❌ POST failed: {e.code} {e.reason}")
    print(e.read().decode())
    sys.exit(1)

# 6. Verify by re-fetch
print("\n=== 5. Verify ===")
v = req("GET", f"{TB}/api/dashboard/{DASHBOARD_ID}", hdr)
verified = 0
for wid, w in v["configuration"]["widgets"].items():
    if wid == target_widget_id:
        for ds in w["config"]["datasources"]:
            for dk in ds.get("dataKeys", []) or []:
                if dk.get("name") == "id":
                    verified += 1 if dk.get("type") == "attribute" else 0
                    print(f"  re-fetched: type='{dk.get('type')}'")

if verified:
    print(f"✅ Verified : `id` is now of type='attribute'")
else:
    print(f"⚠ Verify mismatch — re-check manually")

print("\n=== DONE ===")

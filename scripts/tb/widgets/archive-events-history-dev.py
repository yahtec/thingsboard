#!/usr/bin/env python3
"""
Archive 6 dev versions of tduo.events_history (events_history2..7).
Backups each widget_type JSON before deletion. Idempotent.
"""
import json, sys, urllib.request, urllib.error
from datetime import datetime, timezone

TB = "http://127.0.0.1:8080"
USERNAME = "je@yahtec.com"
PASSWORD = "Yahtec77100"

DEV_FQNS = [f"tduo.events_history{i}" for i in range(2, 8)]
PROD_FQN = "tduo.events_history"

def req(method, url, headers=None, body=None, parse_json=True):
    headers = headers or {}
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r) as resp:
        raw = resp.read()
        return json.loads(raw) if parse_json and raw else raw

# 1. Login
print("=== 1. Login ===")
auth = req("POST", f"{TB}/api/auth/login",
           {"Content-Type": "application/json"},
           {"username": USERNAME, "password": PASSWORD})
jwt = auth["token"]
hdr = {"Content-Type": "application/json", "X-Authorization": f"Bearer {jwt}"}
print(f"JWT acquired ({len(jwt)} chars)")

# 2. Known IDs from SQL audit (avoid endpoint signature quirks)
DEV_IDS = {
    "tduo.events_history2": "d39e0ca0-420b-11f1-bbfe-e1395562cba0",
    "tduo.events_history3": "d7b74610-4316-11f1-bbfe-e1395562cba0",
    "tduo.events_history4": "ba2c78e0-47b7-11f1-a9c9-47ea18512754",
    "tduo.events_history5": "ed4a6e30-43ac-11f1-bbfe-e1395562cba0",
    "tduo.events_history6": "b0a63340-47b9-11f1-a9c9-47ea18512754",
    "tduo.events_history7": "2bbdaa70-47bc-11f1-a9c9-47ea18512754",
}
print("\n=== 2. Targets (from prior SQL audit) ===")
to_delete = []
for fqn, wid in DEV_IDS.items():
    try:
        full = req("GET", f"{TB}/api/widgetType/{wid}", hdr)
        print(f"  GET {fqn:35} → OK (name='{full.get('name')}', fqn='{full.get('fqn')}')")
        to_delete.append({"fqn": fqn, "id": wid, "full": full})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  GET {fqn:35} → 404 (already gone)")
        else:
            print(f"  GET {fqn:35} → {e.code} {e.reason}")
            raise

if not to_delete:
    print("\n✅ Nothing to archive — already done")
    sys.exit(0)

if not to_delete:
    print("\n✅ Nothing to archive — already done")
    sys.exit(0)

# 3. Backup full JSON of each
ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
backup_path = f"/root/backup-widget-types-events-history-dev-{ts}.json"
with open(backup_path, "w") as f:
    json.dump([wt["full"] for wt in to_delete], f, indent=2)
print(f"\n✅ Backup saved: {backup_path} ({len(to_delete)} entries)")

# 4. DELETE each
print("\n=== 3. DELETE via REST ===")
deleted = 0
failed = 0
for wt in to_delete:
    fqn = wt['fqn']
    wid = wt['id']
    try:
        req("DELETE", f"{TB}/api/widgetType/{wid}", hdr, parse_json=False)
        print(f"  ✅ DELETED {fqn:35} id={wid}")
        deleted += 1
    except urllib.error.HTTPError as e:
        print(f"  ❌ FAILED  {fqn:35} id={wid}  ({e.code} {e.reason})")
        print(f"     {e.read().decode()[:200]}")
        failed += 1

print(f"\nResult: deleted={deleted} failed={failed}")

# 5. Verify by re-GET each ID — should 404
print("\n=== 4. Verify (re-GET should 404) ===")
all_404 = True
for wt in to_delete:
    try:
        req("GET", f"{TB}/api/widgetType/{wt['id']}", hdr)
        print(f"  ⚠ {wt['fqn']} still present")
        all_404 = False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ✅ {wt['fqn']:35} confirmed gone (404)")
        else:
            print(f"  ⚠ {wt['fqn']} unexpected: {e.code}")
            all_404 = False

if all_404:
    print("\n✅ All 6 dev versions archived. Only prod 'tduo.events_history' remains.")

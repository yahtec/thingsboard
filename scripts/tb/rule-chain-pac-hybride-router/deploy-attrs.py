#!/usr/bin/env python3
"""Deploy TBEL extract attrs v2 node into PAC Hybride Router via TB REST API.

Auth : TB_TOKEN, ou TB_USER + TB_PASS. Cible : TB_URL (defaut 127.0.0.1:8080).
"""
import json
import os
import sys
import urllib.request

TB = os.environ.get("TB_URL", "http://127.0.0.1:8080")
RC_ID = "b6af0570-4226-11f1-bbfe-e1395562cba0"
TBEL_PATH = "/tmp/extract-attrs.tbel"

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

# 2. GET metadata
print("\n=== 2. GET rule chain metadata ===")
meta = req("GET", f"{TB}/api/ruleChain/{RC_ID}/metadata", hdr)
print(f"Current: {len(meta['nodes'])} nodes, {len(meta['connections'])} connections, firstNodeIndex={meta.get('firstNodeIndex')}")

# Backup before modify
with open("/tmp/rule-chain-metadata-backup.json", "w") as f:
    json.dump(meta, f, indent=2)
print("Backup saved to /tmp/rule-chain-metadata-backup.json")

# 3. Find indices of Filter HPs present v2 and MsgType Switch v2
filter_idx = None
switch_idx = None
existing_attrs_idx = None
for i, n in enumerate(meta["nodes"]):
    if n["name"] == "Filter HPs present v2":
        filter_idx = i
    elif n["name"] == "MsgType Switch v2":
        switch_idx = i
    elif n["name"] == "TBEL extract attrs v2":
        existing_attrs_idx = i

print(f"Filter HPs present v2 = node[{filter_idx}]")
print(f"MsgType Switch v2     = node[{switch_idx}]")
if existing_attrs_idx is not None:
    print(f"⚠ TBEL extract attrs v2 already exists at node[{existing_attrs_idx}] — removing first")
    # Remove existing node + connections referencing it
    meta["nodes"].pop(existing_attrs_idx)
    meta["connections"] = [c for c in meta["connections"]
                           if c["fromIndex"] != existing_attrs_idx
                           and c["toIndex"] != existing_attrs_idx]
    # Reindex any connection whose indices were after the removed
    for c in meta["connections"]:
        if c["fromIndex"] > existing_attrs_idx:
            c["fromIndex"] -= 1
        if c["toIndex"] > existing_attrs_idx:
            c["toIndex"] -= 1
    if filter_idx > existing_attrs_idx:
        filter_idx -= 1
    if switch_idx > existing_attrs_idx:
        switch_idx -= 1

if filter_idx is None or switch_idx is None:
    print("ERROR: required nodes not found"); sys.exit(1)

# 4. Build new node
with open(TBEL_PATH) as f:
    tbel = f.read()

new_node = {
    "type": "org.thingsboard.rule.engine.transform.TbTransformMsgNode",
    "name": "TBEL extract attrs v2",
    "configuration": {
        "scriptLang": "TBEL",
        "tbelScript": tbel
    },
    "additionalInfo": {
        "description": "Extract 37 SERVER_SCOPE attrs from pac_v2 nested payload",
        "layoutX": 1400,
        "layoutY": 300
    },
    "debugSettings": None,
    "singletonMode": False
}

new_idx = len(meta["nodes"])
meta["nodes"].append(new_node)
print(f"\n=== 3. Adding node 'TBEL extract attrs v2' at index {new_idx} ===")

# 5. Add 2 connections
meta["connections"].append({"fromIndex": filter_idx, "toIndex": new_idx, "type": "True"})
meta["connections"].append({"fromIndex": new_idx, "toIndex": switch_idx, "type": "Success"})
print(f"Added 2 connections: Filter HPs[{filter_idx}] --True--> NEW[{new_idx}] --Success--> MsgType Switch[{switch_idx}]")

# 6. POST updated metadata
print("\n=== 4. POST updated metadata ===")
last_err = None
for endpoint in [("POST", f"{TB}/api/ruleChain/metadata"),
                 ("PUT",  f"{TB}/api/ruleChain/{RC_ID}/metadata"),
                 ("PUT",  f"{TB}/api/ruleChain/metadata")]:
    try:
        method, url = endpoint
        resp = req(method, url, hdr, meta)
        print(f"✅ {method} {url} success, new state: {len(resp['nodes'])} nodes, {len(resp['connections'])} connections")
        last_err = None
        break
    except urllib.error.HTTPError as e:
        print(f"  {method} {url} → {e.code}")
        last_err = e
if last_err:
    print(f"❌ all attempts failed, last error: {last_err.code} {last_err.reason}")
    print(last_err.read().decode())
    sys.exit(1)

print("\n=== DONE ===")

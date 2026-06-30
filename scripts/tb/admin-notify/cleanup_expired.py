#!/usr/bin/env python3
"""Désactive les comptes TB dont l'attribut `expiration_ts` (SERVER_SCOPE)
est échu. Idempotent : ne retouche pas un compte déjà désactivé.

Cron quotidien (cf. deploy/tb-notify.cron). Action = on bascule
`additionalInfo.userCredentialsEnabled` à False (équivalent du bouton
"Block" de l'UI TB — bloque la connexion sans détruire le compte).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from common import TBClient, setup_logging  # noqa: E402


def main() -> int:
    log = setup_logging("tb-cleanup-expired")
    now_ms = int(time.time() * 1000)
    tb = TBClient()
    users = tb.list_all_users()
    log.info("Scanning %d users for expired accounts", len(users))
    disabled = 0
    for u in users:
        uid = u["id"]["id"]
        try:
            attrs = tb.get_server_attrs("USER", uid, ["expiration_ts"])
        except Exception as e:  # noqa: BLE001
            log.warning("attrs %s KO: %s", uid, e)
            continue
        exp = attrs.get("expiration_ts")
        try:
            exp_ts = int(exp) if exp not in (None, "", 0) else 0
        except (TypeError, ValueError):
            continue
        if not exp_ts or exp_ts > now_ms:
            continue
        # Déjà désactivé ?
        add = u.get("additionalInfo") or {}
        if isinstance(add, dict) and add.get("userCredentialsEnabled") is False:
            continue
        if not isinstance(add, dict):
            add = {}
        add["userCredentialsEnabled"] = False
        add["disabledReason"] = "expired"
        add["disabledAt"] = now_ms
        u["additionalInfo"] = add
        try:
            tb.update_user(u)
            disabled += 1
            log.info("Disabled user %s (%s) — expired %s",
                     u.get("email"), uid,
                     time.strftime("%Y-%m-%d", time.localtime(exp_ts / 1000)))
        except Exception as e:  # noqa: BLE001
            log.warning("disable %s KO: %s", uid, e)
    log.info("Done — %d account(s) disabled", disabled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

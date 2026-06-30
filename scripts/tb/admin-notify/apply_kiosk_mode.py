#!/usr/bin/env python3
"""Applique le mode kiosk à tous les CUSTOMER_USER : dashboard "Unité" en
plein écran + toolbar cachée. Les TENANT_ADMIN sont ignorés. Idempotent.

Settings appliqués dans `user.additionalInfo` :
- homeDashboardId            = <Unité>
- homeDashboardHideToolbar   = True
- defaultDashboardId         = <Unité>
- defaultDashboardFullscreen = True

Usage :
  python apply_kiosk_mode.py          # applique partout
  python apply_kiosk_mode.py --dry    # liste ce qui serait modifié
  python apply_kiosk_mode.py --revert # retire les 4 clés (sortie de kiosk)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from common import TBClient, setup_logging  # noqa: E402

DASH_ID = os.environ.get("KIOSK_DASH_ID", "0964da30-3e56-11f1-bbfe-e1395562cba0")
KIOSK_KEYS = {
    "homeDashboardId": DASH_ID,
    "homeDashboardHideToolbar": True,
    "defaultDashboardId": DASH_ID,
    "defaultDashboardFullscreen": True,
}


def main() -> int:
    log = setup_logging("tb-kiosk")
    dry = "--dry" in sys.argv
    revert = "--revert" in sys.argv
    tb = TBClient()
    users = tb.list_all_users()
    log.info("%d users — dashboard cible: %s%s%s",
             len(users), DASH_ID, " (DRY-RUN)" if dry else "", " (REVERT)" if revert else "")
    n_skip = n_changed = 0
    for u in users:
        uid = u["id"]["id"]
        authority = u.get("authority")
        email = u.get("email")
        if authority == "TENANT_ADMIN":
            log.info("skip TENANT_ADMIN %s", email)
            n_skip += 1
            continue
        if authority != "CUSTOMER_USER":
            n_skip += 1
            continue
        add = u.get("additionalInfo") or {}
        if not isinstance(add, dict):
            add = {}

        if revert:
            removed = [k for k in KIOSK_KEYS if k in add]
            if not removed:
                log.info("skip %s (déjà hors kiosk)", email)
                n_skip += 1
                continue
            for k in KIOSK_KEYS:
                add.pop(k, None)
            action = f"retire {removed}"
        else:
            need = {k: v for k, v in KIOSK_KEYS.items() if add.get(k) != v}
            if not need:
                log.info("skip %s (déjà en kiosk)", email)
                n_skip += 1
                continue
            add.update(KIOSK_KEYS)
            action = f"pose {list(need)}"

        u["additionalInfo"] = add
        if dry:
            log.info("DRY %s → %s", email, action)
            n_changed += 1
            continue
        try:
            tb.update_user(u)
            log.info("OK  %s → %s", email, action)
            n_changed += 1
        except Exception as e:  # noqa: BLE001
            log.error("KO  %s: %s", email, e)
    log.info("Total: %d modifié(s), %d ignoré(s)", n_changed, n_skip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

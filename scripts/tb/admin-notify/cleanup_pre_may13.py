#!/usr/bin/env python3
"""One-shot cleanup: delete evt_* timeseries strictly before 2026-05-13 00:00
Europe/Paris on every 'pac hybride' device, then reset notification cursors.

Reason: a bug in the device-side firmware (fixed 2026-05-13) caused
'resolved' events (evt_type=4) not to be emitted properly. Historical evt_*
data is unreliable and inflates the digest with phantom 'open' faults.

Usage:
  python3 cleanup_pre_may13.py            # dry-run, prints what would be deleted
  python3 cleanup_pre_may13.py --apply    # actually deletes
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

from common import EVT_KEYS, TBClient, setup_logging

log = setup_logging("cleanup-pre-may13")

CUTOFF = dt.datetime(2026, 5, 13, 0, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
CUTOFF_MS = int(CUTOFF.timestamp() * 1000)
RESET_ATTR_KEYS = ["last_notified_evt_ts", "recent_fault_notifs"]


def main() -> int:
    apply = "--apply" in sys.argv
    tb = TBClient()
    profile = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
    devices = tb.list_devices_by_profile(profile)
    log.info("found %d devices (profile=%r), cutoff = %s = %d ms",
             len(devices), profile, CUTOFF.isoformat(), CUTOFF_MS)

    total = 0
    per_dev: list[tuple[dict, int]] = []
    for d in devices:
        ts = tb.get_timeseries(d["id"]["id"], EVT_KEYS, 0, CUTOFF_MS - 1, limit=100000)
        n = sum(len(v) for v in ts.values())
        per_dev.append((d, n))
        total += n
        log.info("  device=%s  %d points to delete", d["name"], n)

    log.info("TOTAL: %d points across %d devices", total, len(devices))

    if not apply:
        log.info("DRY-RUN — re-run with --apply to delete")
        return 0

    tb._auth()
    for d, n in per_dev:
        dev_id = d["id"]["id"]
        if n > 0:
            path = (f"/api/plugins/telemetry/DEVICE/{dev_id}/timeseries/delete"
                    f"?keys={','.join(EVT_KEYS)}"
                    f"&deleteAllDataForKeys=false&startTs=0&endTs={CUTOFF_MS}"
                    f"&rewriteLatestIfDeleted=true")
            r = tb.s.delete(f"{tb.url}{path}", timeout=120)
            r.raise_for_status()
            log.info("  device=%s  deleted %d points", d["name"], n)

        path = (f"/api/plugins/telemetry/DEVICE/{dev_id}/SERVER_SCOPE"
                f"?keys={','.join(RESET_ATTR_KEYS)}")
        r = tb.s.delete(f"{tb.url}{path}", timeout=30)
        if r.status_code in (200, 204):
            log.info("  device=%s  reset attrs %s", d["name"], RESET_ATTR_KEYS)
        else:
            log.warning("  device=%s  attr reset HTTP %d: %s",
                        d["name"], r.status_code, r.text[:200])

    log.info("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())

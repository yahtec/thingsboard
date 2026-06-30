#!/usr/bin/env python3
"""Cron 1/min: send mail to chaufferie managers when new faults appear.

Behavior:
  - For each `pac hybride` device, read evt_* telemetry between
    `last_notified_evt_ts` (cursor) and now-COALESCE_S (so rafales group).
  - Pair appearance/resolution as the dashboard widget does.
  - For each new appearance whose ts ∈ (cursor, now-COALESCE], notify the
    `gestionnaires` server-attribute of that device.
  - Coalesce all faults of one device into a single mail.
  - Advance the cursor only on success.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import sys
import time
from html import escape

from common import (
    EVT_KEYS, TBClient, collect_records, label_device, label_fault, open_faults,
    pair_events, send_mail, setup_logging,
)

COALESCE_S = 60
LOOKBACK_DEFAULT_S = 300        # cold start: only look at last 5 min
LOOKBACK_MAX_S = 24 * 3600      # safety cap: never scan more than 24h in one shot
COOLDOWN_S = 6 * 3600           # don't re-notify same (device, fault) within 6h
COOLDOWN_GC_S = 24 * 3600       # drop cooldown entries older than this
LOCK_PATH = "/tmp/tb-notify-fault.lock"
log = setup_logging("fault_notify")


def fmt_ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%d/%m/%Y %H:%M:%S")


def render_mail(device_name: str, address: str | None, faults: list) -> tuple[str, str]:
    rows = []
    for e in faults:
        rows.append(
            "<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{fmt_ts(e.appear_ts)}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{escape(label_fault(e.fault))}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#555'>{escape(label_device(e.device))}</td>"
            "</tr>"
        )
    plural = "s" if len(faults) > 1 else ""
    addr_html = f"<div style='color:#6b7280;font-size:13px;margin-top:3px'>{escape(address)}</div>" if address else ""
    html = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222;background:#f6f7f9;margin:0;padding:24px">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);border-top:3px solid #d64545">
  <div style="padding:16px 20px;border-bottom:1px solid #eef0f2">
    <div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#c0392b"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#d64545;margin-right:7px;vertical-align:middle"></span>Nouveau défaut</div>
    <div style="font-size:20px;font-weight:600;margin-top:5px;color:#1c2533">{escape(device_name)}</div>
    {addr_html}
  </div>
  <div style="padding:18px 20px">
    <p style="margin:0 0 14px">{len(faults)} nouveau{plural} défaut{plural} détecté{plural} sur cette chaufferie&nbsp;:</p>
    <table style="border-collapse:collapse;width:100%;font-size:14px">
      <thead><tr style="background:#fafafa">
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Apparition</th>
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Défaut</th>
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Sous-équipement</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
  <div style="background:#fafafa;color:#888;padding:12px 20px;font-size:12px;border-top:1px solid #eee">
    Notification automatique &middot; {fmt_ts(int(time.time()*1000))}
  </div>
</div></body></html>"""
    return html, _plain(device_name, address, faults)


def _plain(device_name: str, address: str | None, faults: list) -> str:
    lines = [f"Nouveau défaut sur {device_name}"]
    if address:
        lines.append(address)
    lines.append("")
    for e in faults:
        lines.append(f"  {fmt_ts(e.appear_ts)}  {label_fault(e.fault)}  ({label_device(e.device)})")
    lines.append("")
    return "\n".join(lines)


def _load_cooldown(raw) -> dict[str, int]:
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _gc_cooldown(cooldown: dict[str, int], now_ms: int) -> dict[str, int]:
    threshold = now_ms - COOLDOWN_GC_S * 1000
    return {k: v for k, v in cooldown.items() if v >= threshold}


def process_device(tb: TBClient, dev: dict, now_ms: int, cutoff_ms: int,
                   users: list[dict] | None = None) -> None:
    dev_id = dev["id"]["id"]
    dev_name = dev["name"]
    attrs = tb.get_server_attrs("DEVICE", dev_id, [
        "last_notified_evt_ts", "recent_fault_notifs",
        "nom_residence", "nom_alternatif", "adresse",
    ])
    cursor = int(attrs.get("last_notified_evt_ts") or (now_ms - LOOKBACK_DEFAULT_S * 1000))
    cursor = max(cursor, now_ms - LOOKBACK_MAX_S * 1000)
    cooldown = _load_cooldown(attrs.get("recent_fault_notifs"))

    # Destinataires = users TB ayant accès à cette chaufferie (admins + ceux
    # qui ont ce deviceId dans leur attribut `chaufferies`). Les comptes
    # désactivés (userCredentialsEnabled=false) sont exclus en amont.
    emails = tb.get_recipients_for_device(dev_id, users)
    if not emails:
        log.info("device=%s skip: no recipients (aucun user TB n'a accès)", dev_name)
        return

    if cursor >= cutoff_ms:
        return  # nothing to scan yet

    ts_data = tb.get_timeseries(dev_id, EVT_KEYS, cursor + 1, cutoff_ms)
    records = collect_records(ts_data)
    if not records:
        tb.save_server_attrs("DEVICE", dev_id, {"last_notified_evt_ts": cutoff_ms})
        return

    events = pair_events(records)
    new_appearances = [e for e in events if e.type == 1 and e.appear_ts and cursor < e.appear_ts <= cutoff_ms]
    new_appearances.sort(key=lambda e: e.appear_ts)

    to_notify, skipped = [], 0
    cooldown_ms = COOLDOWN_S * 1000
    for e in new_appearances:
        key = f"{e.device}|{e.fault}"
        last = int(cooldown.get(key, 0))
        if e.appear_ts >= last + cooldown_ms:
            to_notify.append(e)
            cooldown[key] = e.appear_ts
        else:
            skipped += 1

    if skipped:
        log.info("device=%s skipped %d apparitions within 6h cooldown", dev_name, skipped)

    if to_notify:
        display = attrs.get("nom_residence") or attrs.get("nom_alternatif") or dev_name
        addr = attrs.get("adresse") or ""
        html, text = render_mail(display, addr, to_notify)
        subject = (f"[TDUO] {display} — défaut: {label_fault(to_notify[0].fault)}"
                   if len(to_notify) == 1
                   else f"[TDUO] {display} — {len(to_notify)} nouveaux défauts")
        send_mail(emails, subject, html, text)
        log.info("device=%s sent %d faults to %s", dev_name, len(to_notify), ", ".join(emails))

    cooldown = _gc_cooldown(cooldown, now_ms)
    advance = max((r["ts"] for r in records), default=cutoff_ms)
    tb.save_server_attrs("DEVICE", dev_id, {
        "last_notified_evt_ts": advance,
        "recent_fault_notifs": cooldown,
    })


def main() -> int:
    profile = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another instance is running, exiting")
        return 0

    now_ms = int(time.time() * 1000)
    cutoff = now_ms - COALESCE_S * 1000
    tb = TBClient()
    devices = tb.list_devices_by_profile(profile)
    # On précharge la liste users une fois (au lieu d'un appel par device).
    users = tb._collect_user_attrs()
    log.info("scanning %d devices (profile=%r) — %d users TB connus", len(devices), profile, len(users))
    errors = 0
    for d in devices:
        try:
            process_device(tb, d, now_ms, cutoff, users)
        except Exception as exc:
            errors += 1
            log.exception("device=%s failed: %s", d["name"], exc)
    log.info("done (errors=%d)", errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

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
import os
import sys
import time
from html import escape

try:
    import fcntl  # POSIX only (prod = Linux) ; absent sur les postes dev Windows,
    # ou seul process_device() est teste unitairement (main() n'y est jamais appele).
except ImportError:  # pragma: no cover
    fcntl = None

from common import (
    EVT_KEYS, Event, TBClient, collect_records, label_device, label_fault,
    load_int_map, load_state_attr, mail_grace_ms, open_faults, pair_events,
    send_mail, setup_logging,
)

COALESCE_S = 60
LOOKBACK_DEFAULT_S = 300        # cold start: only look at last 5 min
LOOKBACK_MAX_S = 24 * 3600      # safety cap: never scan more than 24h in one shot
COOLDOWN_S = 6 * 3600           # don't re-notify same (device, fault) within 6h
COOLDOWN_GC_S = 24 * 3600       # drop cooldown entries older than this
NOTIFY_STATE_ATTR = "notify_open_faults"
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
    return load_int_map(raw)


def _gc_cooldown(cooldown: dict[str, int], now_ms: int) -> dict[str, int]:
    threshold = now_ms - COOLDOWN_GC_S * 1000
    return {k: v for k, v in cooldown.items() if v >= threshold}


def _load_notify_state(raw) -> dict[str, dict]:
    """Memoire des defauts suivis par CE script, indexee "<device>|<fault>"
    (meme convention que le cooldown, l'inverse de celle du digest).
    Une entree inexploitable est ignoree seule ; un attribut corrompu vaut
    memoire vide (spec §5.3)."""
    out: dict[str, dict] = {}
    for key, val in load_state_attr(raw).items():
        if not isinstance(val, dict):
            continue
        try:
            out[str(key)] = {
                "appear_ts": int(val["appear_ts"]),
                "mails": int(val.get("mails", 0)),
                "last_mail_ts": int(val.get("last_mail_ts", 0)),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _synthetic(key: str, entry: dict) -> Event | None:
    """Reconstruit un Event affichable depuis une entree memorisee : le mail
    part potentiellement bien apres le run qui a vu l'apparition, l'evenement
    d'origine n'est donc plus dans la fenetre scannee."""
    parts = key.split("|")
    if len(parts) != 2:
        return None
    try:
        device, fault = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    ts = entry["appear_ts"]
    return Event(ts=ts, appear_ts=ts, type=1, fault=fault, device=device,
                 status=0, fault_src=-1, evt_id=0)


def process_device(tb: TBClient, dev: dict, now_ms: int, cutoff_ms: int,
                   users: list[dict] | None = None) -> None:
    dev_id = dev["id"]["id"]
    dev_name = dev["name"]
    attrs = tb.get_server_attrs("DEVICE", dev_id, [
        "last_notified_evt_ts", "recent_fault_notifs", NOTIFY_STATE_ATTR,
        "nom_residence", "nom_alternatif", "adresse",
    ])
    cursor = int(attrs.get("last_notified_evt_ts") or (now_ms - LOOKBACK_DEFAULT_S * 1000))
    cursor = max(cursor, now_ms - LOOKBACK_MAX_S * 1000)
    cooldown = _load_cooldown(attrs.get("recent_fault_notifs"))
    tracked = _load_notify_state(attrs.get(NOTIFY_STATE_ATTR))

    # ── 1. Detection : inscrire les nouveautes, retirer les resolutions ──
    advance = cursor
    if cursor < cutoff_ms:
        records = collect_records(tb.get_timeseries(dev_id, EVT_KEYS, cursor + 1, cutoff_ms))
        if not records:
            advance = cutoff_ms
        else:
            advance = max(r["ts"] for r in records)
            events = pair_events(records)
            for e in events:
                if e.resolved_ts is not None:
                    tracked.pop(f"{e.device}|{e.fault}", None)
            new_appearances = [e for e in events
                               if e.type == 1 and e.appear_ts
                               and cursor < e.appear_ts <= cutoff_ms]
            new_appearances.sort(key=lambda e: e.appear_ts)
            skipped = 0
            for e in new_appearances:
                key = f"{e.device}|{e.fault}"
                if key in tracked:
                    continue  # deja suivi
                if e.appear_ts < int(cooldown.get(key, 0)) + COOLDOWN_S * 1000:
                    skipped += 1
                    continue  # anti-rebond 6 h : pas de nouveau cycle
                tracked[key] = {"appear_ts": e.appear_ts, "mails": 0, "last_mail_ts": 0}
                cooldown[key] = e.appear_ts
            if skipped:
                log.info("device=%s %d apparition(s) dans le cooldown 6h", dev_name, skipped)

    # ── 2. Echeances : sursis ecoule -> mail d'apparition ──
    grace_ms = mail_grace_ms()
    fresh = sorted(k for k, v in tracked.items()
                   if v["mails"] == 0 and now_ms - v["appear_ts"] >= grace_ms)
    if fresh:
        faults = [ev for ev in (_synthetic(k, tracked[k]) for k in fresh) if ev]
        emails = tb.get_recipients_for_device(dev_id, users)
        if emails and faults:
            display = attrs.get("nom_residence") or attrs.get("nom_alternatif") or dev_name
            addr = attrs.get("adresse") or ""
            html, text = render_mail(display, addr, faults)
            subject = (f"[TDUO] {display} — défaut: {label_fault(faults[0].fault)}"
                       if len(faults) == 1
                       else f"[TDUO] {display} — {len(faults)} nouveaux défauts")
            send_mail(emails, subject, html, text)
            log.info("device=%s %d defaut(s) envoye(s) a %s", dev_name, len(faults), ", ".join(emails))
        else:
            log.info("device=%s %d defaut(s) mur(s) mais aucun destinataire — non envoye",
                     dev_name, len(fresh))
        # L'echeance est consommee meme sans destinataire : sinon elle se
        # redeclencherait a chaque run indefiniment (esprit de M18).
        for key in fresh:
            tracked[key]["mails"] = 1
            tracked[key]["last_mail_ts"] = now_ms

    cooldown = _gc_cooldown(cooldown, now_ms)
    tb.save_server_attrs("DEVICE", dev_id, {
        "last_notified_evt_ts": advance,
        "recent_fault_notifs": cooldown,
        NOTIFY_STATE_ATTR: tracked,
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

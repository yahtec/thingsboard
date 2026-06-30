#!/usr/bin/env python3
"""Cron every 4h: send a single digest mail to parc admins listing every
chaufferie with at least one open fault.

Source of truth = evt_* telemetry (NOT TB alarms — they may stay orphaned).
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from html import escape

from common import (
    EVT_KEYS, TBClient, collect_records, label_device, label_fault, open_faults,
    pair_events, send_mail, setup_logging,
)

LOOKBACK_DAYS = 30  # how far back we scan to reconstruct "open faults" state
log = setup_logging("fault_digest")


def fmt_ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%d/%m/%Y %H:%M:%S")


def get_admin_recipients(tb: TBClient) -> list[str]:
    """Destinataires du digest 4h = comptes TENANT_ADMIN + CUSTOMER_USER+is_admin=true.
    Fallback env PARC_ADMINS_FALLBACK uniquement si la liste TB est vide (filet
    de sécurité pour éviter de perdre le récap si le tenant n'a pas d'admin)."""
    try:
        emails = tb.get_admin_emails()
        if emails:
            return emails
    except Exception as exc:
        log.warning("could not enumerate admin users: %s", exc)
    return [s.strip() for s in os.environ.get("PARC_ADMINS_FALLBACK", "").split(",") if s.strip()]


def collect_open_per_device(tb: TBClient, devices: list[dict], end_ms: int) -> list[dict]:
    out: list[dict] = []
    start_ms = end_ms - LOOKBACK_DAYS * 86400 * 1000
    for d in devices:
        dev_id = d["id"]["id"]
        dev_name = d["name"]
        attrs = tb.get_server_attrs("DEVICE", dev_id, ["nom_residence", "nom_alternatif", "adresse"])
        display = attrs.get("nom_residence") or attrs.get("nom_alternatif") or dev_name
        addr = attrs.get("adresse") or ""
        ts = tb.get_timeseries(dev_id, EVT_KEYS, start_ms, end_ms)
        events = pair_events(collect_records(ts))
        opens = open_faults(events)
        if opens:
            opens.sort(key=lambda e: e.appear_ts or 0)
            out.append({"name": dev_name, "display": display, "address": addr, "faults": opens})
    out.sort(key=lambda x: x["display"].lower())
    return out


def render_digest(per_device: list[dict], generated_ms: int) -> tuple[str, str]:
    sections, plain_lines = [], []
    total = sum(len(v["faults"]) for v in per_device)
    for info in per_device:
        rows = []
        for e in info["faults"]:
            rows.append(
                "<tr>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0'>{fmt_ts(e.appear_ts)}</td>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0'>{escape(label_fault(e.fault))}</td>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;color:#666'>{escape(label_device(e.device))}</td>"
                "</tr>"
            )
        sub_bits = []
        if info["display"] != info["name"]:
            sub_bits.append(info["name"])
        if info["address"]:
            sub_bits.append(info["address"])
        sub = (" <span style='color:#888;font-weight:400'>· " + escape(" · ".join(sub_bits)) + "</span>") if sub_bits else ""
        sections.append(f"""
<div style="margin:18px 0">
  <div style="font-size:15px;font-weight:600;color:#111;margin-bottom:8px">{escape(info['display'])}{sub}
    <span style="float:right;color:#e53935;font-weight:600">{len(info['faults'])} défaut{'s' if len(info['faults'])>1 else ''}</span>
  </div>
  <table style="border-collapse:collapse;width:100%;font-size:13px;background:#fff;border:1px solid #eee;border-radius:6px;overflow:hidden">
    <thead><tr style="background:#fafafa">
      <th style="text-align:left;padding:8px 12px;color:#666;font-weight:600">Apparu le</th>
      <th style="text-align:left;padding:8px 12px;color:#666;font-weight:600">Défaut</th>
      <th style="text-align:left;padding:8px 12px;color:#666;font-weight:600">Sous-équipement</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>""")
        head = info["display"]
        if info["display"] != info["name"]:
            head += f"  [{info['name']}]"
        if info["address"]:
            head += f"  ({info['address']})"
        plain_lines.append(f"\n{head}  — {len(info['faults'])} défaut(s)")
        for e in info["faults"]:
            plain_lines.append(f"  {fmt_ts(e.appear_ts)}  {label_fault(e.fault)}  ({label_device(e.device)})")

    html = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222;background:#f6f7f9;margin:0;padding:24px">
<div style="max-width:780px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="background:#263238;color:#fff;padding:18px 22px">
    <div style="font-size:13px;opacity:.8;text-transform:uppercase;letter-spacing:.5px">Récap parc TDUO</div>
    <div style="font-size:20px;font-weight:600;margin-top:2px">
      {len(per_device)} chaufferie{'s' if len(per_device)>1 else ''} en défaut · {total} défaut{'s' if total>1 else ''} actif{'s' if total>1 else ''}
    </div>
    <div style="font-size:13px;opacity:.7;margin-top:4px">{fmt_ts(generated_ms)}</div>
  </div>
  <div style="padding:6px 22px 22px">{''.join(sections)}</div>
  <div style="background:#fafafa;color:#888;padding:12px 22px;font-size:12px;border-top:1px solid #eee">
    Digest automatique &middot; généré toutes les 4&nbsp;heures s'il y a au moins un défaut actif.
  </div>
</div></body></html>"""
    text = (f"Récap parc TDUO — {len(per_device)} chaufferie(s) en défaut, {total} défaut(s)\n"
            f"Généré le {fmt_ts(generated_ms)}\n" + "\n".join(plain_lines))
    return html, text


def main() -> int:
    profile = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
    tb = TBClient()
    admins = get_admin_recipients(tb)
    if not admins:
        log.error("no admin recipients (set parc_admins or PARC_ADMINS_FALLBACK)")
        return 2

    devices = tb.list_devices_by_profile(profile)
    now_ms = int(time.time() * 1000)
    log.info("scanning %d devices over last %dd", len(devices), LOOKBACK_DAYS)
    per = collect_open_per_device(tb, devices, now_ms)

    if not per:
        log.info("no open faults across parc — silent run")
        return 0

    html, text = render_digest(per, now_ms)
    total = sum(len(v["faults"]) for v in per)
    subject = f"[TDUO] Récap parc — {len(per)} chaufferie(s) en défaut, {total} défaut(s) actif(s)"
    send_mail(admins, subject, html, text)
    log.info("digest sent to %s (%d devices, %d faults)", ", ".join(admins), len(per), total)
    return 0


if __name__ == "__main__":
    sys.exit(main())

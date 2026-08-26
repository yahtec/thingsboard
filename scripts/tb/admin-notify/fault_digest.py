#!/usr/bin/env python3
"""Cron every 4h: send a single digest mail to parc admins listing every
chaufferie with at least one open fault.

Source of truth = evt_* telemetry (NOT TB alarms — they may stay orphaned).

Per-device error isolation (I8)
--------------------------------
`collect_open_per_device` wraps each device's fetch (attrs + timeseries) in
its own try/except (pattern mirrors `fault_notify.main()`'s loop): a device
that errors is logged and skipped for THIS run, it never aborts the digest
for the rest of the parc. Skipped devices are returned separately (`errors`)
and are NOT silently dropped from the mail — `render_digest`/`build_digest`
surface them explicitly (a dedicated "collecte incomplète" notice) so the
digest never presents missing data as "this device has no faults".

Open-fault memory beyond the lookback window (I7)
--------------------------------------------------
`LOOKBACK_DAYS` bounds how far back we *scan* to discover faults, but a
fault that appeared before that window and was never resolved would
otherwise silently fall out of every future digest — exactly the faults
that most need admin attention. To fix this without scanning an
ever-growing window, each device carries its own memory:

  SERVER_SCOPE attribute `digest_open_faults` (device entity) — a JSON dict
  `{"<fault>|<device>": appear_ts_ms, ...}` of faults last known to be open.
  This mirrors how `fault_notify.py` persists its own per-device state
  (`last_notified_evt_ts` cursor, `recent_fault_notifs` cooldown) as
  SERVER_SCOPE attributes rather than a local file — same storage
  mechanism/location convention, applied here to open-fault memory.

Each run, per device:
  - keys whose fault is resolved somewhere in this run's window (a type=4
    seen for that `fault|device`) are dropped from the memory;
  - keys still open (no resolution seen — whether the original appearance
    is inside or outside this run's window) are carried forward. When the
    appearance record itself has scrolled out of the window, a synthetic
    `Event` is rebuilt from the remembered `appear_ts` so it still renders;
  - fresh appearances discovered in this run's window are added/refreshed
    with their real ts.
  - the merged result is written back unconditionally (even `{}`) so a
    resolved fault's entry is actually cleared, not just skipped this once.

A missing or corrupted attribute value (wrong JSON, wrong type, garbage
string) is treated as an empty state — start fresh, never crash the digest.

A device that disappears from the fleet (no longer returned by
`list_devices_by_profile`) needs no separate pruning pass: the memory lives
ON that device's own entity, not in a shared/global blob, so an orphaned
device's leftover attribute is simply never revisited or written again —
it does not pollute other devices' state.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from html import escape

from common import (
    EVT_KEYS, Event, TBClient, collect_records, excluded_device_names,
    filter_excluded, label_device, label_fault, load_int_map, open_faults,
    pair_events, send_mail, setup_logging,
)

LOOKBACK_DAYS = 30  # how far back we scan to *discover* new open faults
STATE_ATTR = "digest_open_faults"  # per-device SERVER_SCOPE memory, see module docstring (I7)

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


def _load_open_state(raw) -> dict[str, int]:
    """Cf. common.load_int_map — conserve comme point d'entree nomme pour que
    le docstring du module (I7) reste lisible."""
    return load_int_map(raw)


def _process_device(tb: TBClient, d: dict, start_ms: int, end_ms: int) -> dict | None:
    """Fetch + reconcile one device. Raises on I/O failure — the caller
    (`collect_open_per_device`) isolates that per device (I8)."""
    dev_id = d["id"]["id"]
    dev_name = d["name"]
    attrs = tb.get_server_attrs(
        "DEVICE", dev_id, ["nom_residence", "nom_alternatif", "adresse", STATE_ATTR],
    )
    ts = tb.get_timeseries(dev_id, EVT_KEYS, start_ms, end_ms)

    display = attrs.get("nom_residence") or attrs.get("nom_alternatif") or dev_name
    addr = attrs.get("adresse") or ""
    events = pair_events(collect_records(ts))
    opens_in_window = open_faults(events)
    resolved_keys = {f"{e.fault}|{e.device}" for e in events if e.resolved_ts is not None}

    carried = _load_open_state(attrs.get(STATE_ATTR))
    synthetic: dict[str, Event] = {}
    new_state: dict[str, int] = {}

    for key, appear_ts in carried.items():
        if key in resolved_keys:
            continue  # resolution observed this run -> memory cleared (I7)
        try:
            fault_s, dev_s = key.split("|", 1)
            fault_code, dev_code = int(fault_s), int(dev_s)
        except (ValueError, TypeError):
            continue  # malformed key -> drop silently, do not propagate
        synthetic[key] = Event(
            ts=appear_ts, appear_ts=appear_ts, type=1,
            fault=fault_code, device=dev_code, status=0, fault_src=-1, evt_id=0,
        )
        new_state[key] = appear_ts

    for e in opens_in_window:
        key = f"{e.fault}|{e.device}"
        synthetic[key] = e  # prefer the fully-populated event when we have it
        new_state[key] = e.appear_ts

    try:
        tb.save_server_attrs("DEVICE", dev_id, {STATE_ATTR: new_state})
    except Exception as exc:
        log.warning("device=%s could not persist %s (will retry next run): %s", dev_name, STATE_ATTR, exc)

    if not synthetic:
        return None
    opens = sorted(synthetic.values(), key=lambda e: e.appear_ts or 0)
    return {"name": dev_name, "display": display, "address": addr, "faults": opens}


def collect_open_per_device(tb: TBClient, devices: list[dict], end_ms: int) -> tuple[list[dict], list[str]]:
    """Returns (per_device_info, errored_device_names). A device whose fetch
    fails is logged + skipped (I8) — it never aborts the rest of the parc."""
    out: list[dict] = []
    errors: list[str] = []
    start_ms = end_ms - LOOKBACK_DAYS * 86400 * 1000
    for d in devices:
        dev_name = d.get("name", "?")
        try:
            info = _process_device(tb, d, start_ms, end_ms)
        except Exception as exc:
            errors.append(dev_name)
            log.exception("device=%s failed to collect — skipped this run: %s", dev_name, exc)
            continue
        if info:
            out.append(info)
    out.sort(key=lambda x: x["display"].lower())
    return out, errors


def render_digest(per_device: list[dict], generated_ms: int,
                  errors: list[str] | None = None) -> tuple[str, str]:
    """errors = device names skipped this run (I8) — surfaced explicitly so
    the digest never presents a collection failure as "no faults there"."""
    errors = errors or []
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

    error_html, error_text = "", ""
    if errors:
        names = ", ".join(escape(e) for e in errors)
        plural = "s" if len(errors) > 1 else ""
        verb = "n'ont" if plural else "n'a"
        error_html = f"""
<div style="margin:0 0 18px;padding:12px 14px;background:#fff8e1;border:1px solid #ffe082;border-radius:6px;color:#7a5b00;font-size:13px">
  ⚠ Collecte incomplète — {len(errors)} device{plural} {verb} pas pu être interrogé{plural} ce cycle (statut de défaut non reflété ci-dessous, nouvelle tentative au prochain cycle) : {names}.
</div>"""
        error_text = (f"\n⚠ Collecte incomplète — {len(errors)} device(s) non interrogé(s) ce cycle "
                       f"(statut non reflété, nouvelle tentative au prochain cycle) : "
                       + ", ".join(errors) + "\n")

    html = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222;background:#f6f7f9;margin:0;padding:24px">
<div style="max-width:780px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="background:#263238;color:#fff;padding:18px 22px">
    <div style="font-size:13px;opacity:.8;text-transform:uppercase;letter-spacing:.5px">Récap parc TDUO</div>
    <div style="font-size:20px;font-weight:600;margin-top:2px">
      {len(per_device)} chaufferie{'s' if len(per_device)>1 else ''} en défaut · {total} défaut{'s' if total>1 else ''} actif{'s' if total>1 else ''}
    </div>
    <div style="font-size:13px;opacity:.7;margin-top:4px">{fmt_ts(generated_ms)}</div>
  </div>
  <div style="padding:6px 22px 22px">{error_html}{''.join(sections)}</div>
  <div style="background:#fafafa;color:#888;padding:12px 22px;font-size:12px;border-top:1px solid #eee">
    Digest automatique &middot; généré toutes les 4&nbsp;heures s'il y a au moins un défaut actif.
  </div>
</div></body></html>"""
    text = (f"Récap parc TDUO — {len(per_device)} chaufferie(s) en défaut, {total} défaut(s)\n"
            f"Généré le {fmt_ts(generated_ms)}\n" + error_text + "\n".join(plain_lines))
    return html, text


def build_digest(per_device: list[dict], errors: list[str],
                 generated_ms: int) -> tuple[str, str, str] | None:
    """Decide whether the 4h cron has anything to report and build the mail.
    Returns (subject, html, text), or None only when there is truly nothing
    to say (no open fault AND no collection error) — a run with errors but
    zero known-open faults still sends, so a collection failure is never
    mistaken for "parc clean" (see module docstring, I8)."""
    if not per_device and not errors:
        return None
    html, text = render_digest(per_device, generated_ms, errors)
    total = sum(len(v["faults"]) for v in per_device)
    bits = []
    if per_device:
        bits.append(f"{len(per_device)} chaufferie(s) en défaut, {total} défaut(s) actif(s)")
    if errors:
        bits.append(f"{len(errors)} device(s) en erreur")
    subject = "[TDUO] Récap parc — " + " · ".join(bits)
    return subject, html, text


def main() -> int:
    profile = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
    tb = TBClient()
    admins = get_admin_recipients(tb)
    if not admins:
        log.error("no admin recipients (set parc_admins or PARC_ADMINS_FALLBACK)")
        return 2

    devices = tb.list_devices_by_profile(profile)
    devices, dropped = filter_excluded(devices, excluded_device_names())
    if dropped:
        log.info("digest: %d device(s) exclus du récap: %s", len(dropped), ", ".join(sorted(dropped)))
    now_ms = int(time.time() * 1000)
    log.info("scanning %d devices over last %dd", len(devices), LOOKBACK_DAYS)
    per, errors = collect_open_per_device(tb, devices, now_ms)

    built = build_digest(per, errors, now_ms)
    if built is None:
        log.info("no open faults across parc and no collection errors — silent run")
        return 0

    subject, html, text = built
    send_mail(admins, subject, html, text)
    total = sum(len(v["faults"]) for v in per)
    log.info("digest sent to %s (%d devices, %d faults, %d errors)",
              ", ".join(admins), len(per), total, len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())

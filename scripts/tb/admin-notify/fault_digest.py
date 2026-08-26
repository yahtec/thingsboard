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
    EVT_KEYS, Event, TBClient, collect_records, digest_fast_quota_ms,
    digest_min_gap_ms, digest_recap_hour as common_recap_hour,
    excluded_device_names, filter_excluded, label_device, label_fault,
    load_int_map, mail_grace_ms, open_faults, pair_events, send_mail,
    setup_logging,
)

LOOKBACK_DAYS = 30  # how far back we scan to *discover* new open faults
STATE_ATTR = "digest_open_faults"  # per-device SERVER_SCOPE memory, see module docstring (I7)

log = setup_logging("fault_digest")


def fmt_ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%d/%m/%Y %H:%M:%S")


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
    # `carried` = memoire telle qu'elle etait AVANT l'ecriture de ce run.
    # Vide => la chaufferie etait saine au run precedent, ce qui la rend
    # candidate au mail rapide (spec §4.1). On garde meme les cles resolues
    # ce run : la chaufferie etait bel et bien en defaut au run precedent.
    return {"id": dev_id, "name": dev_name, "display": display, "address": addr,
            "faults": opens, "carried": set(carried)}


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


# ─── Machine a etats du recap, par destinataire (spec §4.1) ────────────────

def _local_anchor_ms(now_ms: int, hour: int) -> int:
    """Ancre du jour de `now_ms` : ce jour-la a `hour`:00 en heure LOCALE.
    Le quotidien est ancre sur une heure de la journee et non sur un delai
    glissant : un delai glissant evalue par un cron horaire repousse chaque
    envoi d'un peu plus de 24 h et finit par faire le tour du cadran."""
    day = dt.datetime.fromtimestamp(now_ms / 1000)
    anchor = day.replace(hour=hour, minute=0, second=0, microsecond=0)
    return int(anchor.timestamp() * 1000)


def decide_mail(per_device: list[dict], state: dict[str, int], now_ms: int,
                cfg: dict, has_errors: bool = False) -> tuple[str | None, dict[str, int]]:
    """Decide s'il faut envoyer un mail a UN destinataire, et lequel.

    per_device  chaufferies de SON perimetre ayant au moins un defaut ouvert,
                telles que rendues par `_process_device` (cles `id`, `faults`,
                `carried`). Liste vide = perimetre sain.
    state       {"last_mail_ts", "last_fast_ts"} lu sur l'utilisateur.
    cfg         {"grace_ms", "recap_hour", "min_gap_ms", "fast_quota_ms"}.
    has_errors  au moins une chaufferie de son perimetre a echoue a la
                collecte ce run (invariant I8).

    Retourne (kind, new_state), kind ∈ {None, "fast", "daily"}.
    Fonction pure : aucun I/O, tout le temps passe par now_ms.
    """
    last_mail = int(state.get("last_mail_ts") or 0)
    last_fast = int(state.get("last_fast_ts") or 0)

    if not per_device and not has_errors:
        # Fin d'episode : les DEUX horodatages survivent. Ce sont des limiteurs
        # de debit, pas des etats d'episode (spec §4.1 point 1). Remettre
        # last_mail_ts a 0 ici libererait d'un coup les deux freins du
        # quotidien — ils lisent le meme horodatage — et un defaut qui bat de
        # l'aile produirait plusieurs recaps dans la meme journee.
        return None, {"last_mail_ts": last_mail, "last_fast_ts": last_fast}

    # Mail rapide : une chaufferie sans memoire au run precedent (`carried`
    # vide) vient d'entrer en defaut, et son sursis est ecoule. Un echec de
    # collecte n'est jamais une apparition de defaut : il n'entre pas ici.
    fast_candidate = False
    for info in per_device:
        if info.get("carried"):
            continue
        appears = [e.appear_ts for e in info["faults"] if e.appear_ts]
        if appears and now_ms - min(appears) >= cfg["grace_ms"]:
            fast_candidate = True
            break
    if fast_candidate and now_ms - last_fast >= cfg["fast_quota_ms"]:
        return "fast", {"last_mail_ts": now_ms, "last_fast_ts": now_ms}

    # Quotidien ancre. `last_mail < ancre` interdit un deuxieme envoi aux runs
    # suivants de la meme journee. `established` interdit au quotidien de
    # court-circuiter le sursis : sans lui, un defaut apparu a 14 h un jour ou
    # le perimetre etait sain partirait des le run de 14 h (ancre passee,
    # last_mail a 0). Une chaufferie en echec de collecte compte comme
    # etablie : une panne persistante doit ressortir une fois par jour (I8).
    established = has_errors or any(info.get("carried") for info in per_device)
    anchor = _local_anchor_ms(now_ms, cfg["recap_hour"])
    if (established and now_ms >= anchor and last_mail < anchor
            and now_ms - last_mail >= cfg["min_gap_ms"]):
        return "daily", {"last_mail_ts": now_ms, "last_fast_ts": last_fast}

    return None, {"last_mail_ts": last_mail, "last_fast_ts": last_fast}


def send_for_target(tb: TBClient, target: dict, per_device: list[dict],
                    errors: list[str], id_of_name: dict[str, str],
                    now_ms: int, cfg: dict) -> str | None:
    """Evalue la cadence d'UN destinataire, envoie si c'est du, persiste son
    etat. L'etat est ecrit meme quand rien n'est envoye : c'est lui qui porte
    la fin d'episode."""
    excl = target["exclude"]
    scope = [i for i in per_device if i["id"] not in excl]
    # `errors` est une liste de NOMS de devices ; les exclusions sont des ids.
    errs = [n for n in errors if id_of_name.get(n) not in excl]

    kind, new_state = decide_mail(scope, tb.get_digest_state(target["id"]),
                                  now_ms, cfg, has_errors=bool(errs))
    if kind:
        built = build_digest(scope, errs, now_ms)
        if built is None:
            # Defensif : decide_mail ne rend un kind que si scope ou errs est
            # non vide, donc build_digest ne peut pas rendre None ici.
            kind = None
        else:
            subject, html, text = built
            send_mail([target["email"]], subject, html, text)
            log.info("digest %s -> %s (%d chaufferie(s), %d erreur(s))",
                     kind, target["email"], len(scope), len(errs))
    tb.save_digest_state(target["id"], new_state)
    return kind


def fallback_daily(per_device: list[dict], errors: list[str], now_ms: int) -> int:
    """Filet de securite : TB ne rend aucun admin (base cassee ou mal
    configuree). Sans utilisateur il n'y a pas d'attribut d'etat, donc pas de
    cadence persistee ; on s'appuie sur le fait que l'heure d'ancrage n'est
    vraie qu'a un seul run horaire par jour, ce qui borne l'envoi a 1/jour
    sans rien stocker. Pas de mail rapide dans ce mode degrade."""
    emails = [s.strip() for s in os.environ.get("PARC_ADMINS_FALLBACK", "").split(",") if s.strip()]
    if not emails:
        log.error("aucun admin en base et PARC_ADMINS_FALLBACK vide — recap perdu")
        return 2
    if dt.datetime.fromtimestamp(now_ms / 1000).hour != common_recap_hour():
        log.warning("aucun admin en base — envoi de secours reporte a %dh", common_recap_hour())
        return 0
    built = build_digest(per_device, errors, now_ms)
    if built is None:
        return 0
    subject, html, text = built
    send_mail(emails, subject, html, text)
    log.warning("aucun admin en base — recap de secours envoye a %s", ", ".join(emails))
    return 0


def main() -> int:
    profile = os.environ.get("TB_DEVICE_PROFILE_NAME", "pac hybride")
    tb = TBClient()

    devices = tb.list_devices_by_profile(profile)
    devices, dropped = filter_excluded(devices, excluded_device_names())
    if dropped:
        log.info("digest: %d chaufferie(s) muette(s): %s", len(dropped), ", ".join(sorted(dropped)))

    now_ms = int(time.time() * 1000)
    log.info("scanning %d devices over last %dd", len(devices), LOOKBACK_DAYS)
    per, errors = collect_open_per_device(tb, devices, now_ms)
    id_of_name = {d["name"]: d["id"]["id"] for d in devices}

    try:
        targets = tb.get_admin_targets()
    except Exception as exc:
        log.warning("could not enumerate admin users: %s", exc)
        targets = []
    if not targets:
        return fallback_daily(per, errors, now_ms)

    cfg = {"grace_ms": mail_grace_ms(), "recap_hour": common_recap_hour(),
           "min_gap_ms": digest_min_gap_ms(), "fast_quota_ms": digest_fast_quota_ms()}
    sent = 0
    for target in targets:
        try:
            if send_for_target(tb, target, per, errors, id_of_name, now_ms, cfg):
                sent += 1
        except Exception as exc:
            # Isolation par destinataire, dans le meme esprit que I8 : un
            # destinataire en echec ne prive pas les autres de leur recap.
            log.exception("destinataire=%s echec — ignore ce run: %s", target["email"], exc)
    log.info("run termine : %d mail(s) envoye(s) sur %d destinataire(s)", sent, len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main())

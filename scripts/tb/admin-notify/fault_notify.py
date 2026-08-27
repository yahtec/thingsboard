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
    reminder_steps_ms as common_reminder_steps, send_mail, setup_logging,
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


def render_reminder(device_name: str, address: str | None, faults: list,
                    now_ms: int) -> tuple[str, str]:
    """Gabarit DISTINCT du mail d'apparition : bandeau ambre, mention de
    l'anciennete. Un client ne doit pas confondre une relance avec un
    nouveau defaut."""
    rows, plain = [], [f"Défaut toujours ouvert sur {device_name}"]
    if address:
        plain.append(address)
    plain.append("")
    for e in faults:
        days = max(0, (now_ms - (e.appear_ts or now_ms)) // 86400000)
        age = "aujourd'hui" if days < 1 else f"depuis {days} jour{'s' if days > 1 else ''}"
        rows.append(
            "<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{fmt_ts(e.appear_ts)}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{escape(label_fault(e.fault))}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#555'>{escape(label_device(e.device))}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#8a6d3b'>{escape(age)}</td>"
            "</tr>"
        )
        plain.append(f"  {fmt_ts(e.appear_ts)}  {label_fault(e.fault)}  ({label_device(e.device)})  {age}")
    plural = "s" if len(faults) > 1 else ""
    addr_html = (f"<div style='color:#6b7280;font-size:13px;margin-top:3px'>{escape(address)}</div>"
                 if address else "")
    html = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222;background:#f6f7f9;margin:0;padding:24px">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);border-top:3px solid #e0a800">
  <div style="padding:16px 20px;border-bottom:1px solid #eef0f2">
    <div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#8a6d3b"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#e0a800;margin-right:7px;vertical-align:middle"></span>Rappel — défaut non résolu</div>
    <div style="font-size:20px;font-weight:600;margin-top:5px;color:#1c2533">{escape(device_name)}</div>
    {addr_html}
  </div>
  <div style="padding:18px 20px">
    <p style="margin:0 0 14px">{len(faults)} défaut{plural} signalé{plural} précédemment {'est' if len(faults) == 1 else 'sont'} toujours ouvert{plural}&nbsp;:</p>
    <table style="border-collapse:collapse;width:100%;font-size:14px">
      <thead><tr style="background:#fafafa">
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Apparition</th>
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Défaut</th>
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Sous-équipement</th>
        <th style="text-align:left;padding:8px 12px;color:#555;font-weight:600;border-bottom:1px solid #eee">Ouvert</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
  <div style="background:#fafafa;color:#888;padding:12px 20px;font-size:12px;border-top:1px solid #eee">
    Rappel automatique &middot; {fmt_ts(now_ms)}
  </div>
</div></body></html>"""
    plain.append("")
    return html, "\n".join(plain)


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


def reminder_due(entry: dict, now_ms: int, steps_ms: list[int]) -> bool:
    """Un rappel est du si le defaut a deja ete annonce (`mails >= 1`) et que
    le palier correspondant a son compteur est ecoule. Au-dela de la liste on
    reste sur le dernier palier : un defaut chronique est relance a la
    frequence la plus lente, indefiniment, jusqu'a resolution."""
    mails = int(entry.get("mails", 0))
    if mails < 1 or not steps_ms:
        return False
    step = steps_ms[min(mails, len(steps_ms)) - 1]
    # Repli sur `appear_ts` si `last_mail_ts` manque : le lire a 0 ferait
    # tomber le rappel immediatement apres le mail d'apparition. Aucun
    # producteur de ce depot n'ecrit l'un sans l'autre, mais un attribut
    # edite a la main ou herite ne doit pas declencher une rafale.
    last = int(entry.get("last_mail_ts") or entry.get("appear_ts", 0))
    return now_ms - last >= step


def _flip_key(key: str) -> str | None:
    """`digest_open_faults` indexe "<fault>|<device>", la memoire de ce script
    et le cooldown indexent "<device>|<fault>". L'amorcage doit donc inverser
    — sinon les defauts amorces ne correspondent a aucune resolution observee
    et ne seraient jamais effaces. On rejette ici ce qui n'est pas une paire
    d'entiers, plutot que de laisser passer une cle que `_synthetic` refusera
    plus tard : une cle illisible en memoire coute une purge et un
    avertissement, autant ne pas l'y mettre."""
    parts = key.split("|")
    if len(parts) != 2:
        return None
    try:
        int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return f"{parts[1]}|{parts[0]}"


def _seed_from_digest(raw, now_ms: int) -> dict[str, dict]:
    """Amorcage au premier run d'une chaufferie (spec §4.2) : les defauts
    deja ouverts au deploiement n'ont pas d'entree et ne seraient donc jamais
    relances — un angle mort permanent sur les defauts en cours. On les
    reprend de la memoire du digest avec `mails=1` (ils ont deja ete annonces
    en leur temps) et `last_mail_ts=now`, donc premier rappel a 24 h."""
    out: dict[str, dict] = {}
    for key, appear_ts in load_int_map(raw).items():
        flipped = _flip_key(key)
        if flipped is None:
            continue
        # Premier chemin ou un `appear_ts` vient d'un attribut ETRANGER et non
        # de `pair_events`. Une valeur absurde afficherait 1970 au client, et
        # une valeur hors bornes ferait lever `fmt_ts` -> `process_device`
        # s'interromprait avant `save_server_attrs`, figeant le curseur de
        # cette chaufferie. On borne donc a un instant passe plausible.
        if not 0 < appear_ts <= now_ms:
            log.warning("device: amorcage ignore, appear_ts hors bornes pour %s: %r",
                        flipped, appear_ts)
            continue
        out[flipped] = {"appear_ts": appear_ts, "mails": 1, "last_mail_ts": now_ms}
    return out


def _mail_batch(emails: list[str], dev_name: str, display: str, addr: str,
                tracked: dict, keys: list[str], now_ms: int,
                reminder: bool) -> None:
    """Un mail par lot (apparitions d'un cote, rappels de l'autre) : les deux
    ne disent pas la meme chose, ils ne doivent pas etre fusionnes.
    `dev_name` est le numero de serie, utilise pour les logs : tous les autres
    logs de ce script identifient les chaufferies par la, et un operateur qui
    grep par serie ne doit pas rater ces lignes. `display` est le nom du site,
    destine au contenu du mail."""
    if not keys:
        return
    faults = [ev for ev in (_synthetic(k, tracked[k]) for k in keys) if ev]
    if not faults:
        return
    if reminder:
        html, text = render_reminder(display, addr, faults, now_ms)
        subject = (f"[TDUO] {display} — défaut toujours ouvert: {label_fault(faults[0].fault)}"
                   if len(faults) == 1
                   else f"[TDUO] {display} — {len(faults)} défauts toujours ouverts")
    else:
        html, text = render_mail(display, addr, faults)
        subject = (f"[TDUO] {display} — défaut: {label_fault(faults[0].fault)}"
                   if len(faults) == 1
                   else f"[TDUO] {display} — {len(faults)} nouveaux défauts")
    send_mail(emails, subject, html, text)
    log.info("device=%s %s: %d defaut(s) -> %s", dev_name,
             "rappel" if reminder else "apparition", len(faults), ", ".join(emails))


def process_device(tb: TBClient, dev: dict, now_ms: int, cutoff_ms: int,
                   users: list[dict] | None = None) -> None:
    dev_id = dev["id"]["id"]
    dev_name = dev["name"]
    attrs = tb.get_server_attrs("DEVICE", dev_id, [
        "last_notified_evt_ts", "recent_fault_notifs", NOTIFY_STATE_ATTR,
        "nom_residence", "nom_alternatif", "adresse", "digest_open_faults",
    ])
    cursor = int(attrs.get("last_notified_evt_ts") or (now_ms - LOOKBACK_DEFAULT_S * 1000))
    cursor = max(cursor, now_ms - LOOKBACK_MAX_S * 1000)
    cooldown = _load_cooldown(attrs.get("recent_fault_notifs"))
    if NOTIFY_STATE_ATTR in attrs:
        tracked = _load_notify_state(attrs.get(NOTIFY_STATE_ATTR))
    else:
        tracked = _seed_from_digest(attrs.get("digest_open_faults"), now_ms)

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
            # `e.resolved_ts is None` est ESSENTIEL, et c'est le meme critere
            # que `common.open_faults` qu'utilise le digest. `pair_events` ne
            # produit pas deux evenements pour un couple apparition/resolution :
            # sur un type=4 il complete l'evenement de type 1 EN PLACE
            # (common.py, `o.resolved_ts = r["ts"]`) sans rien ajouter a la
            # liste, et sans aucune fenetre de temps. Un defaut apparu ET
            # resolu dans une meme fenetre de scan est donc un unique evenement
            # de type 1 portant deja `resolved_ts`. Sans ce filtre il serait
            # inscrit, puis notifie une heure plus tard alors qu'il est clos —
            # et sa resolution etant passee derriere le curseur, rien ne
            # l'effacerait jamais. C'est exactement le defaut de communication
            # qui bat de l'aile que ce chantier existe pour taire.
            new_appearances = [e for e in events
                               if e.type == 1 and e.appear_ts and e.resolved_ts is None
                               and cursor < e.appear_ts <= cutoff_ms]
            new_appearances.sort(key=lambda e: e.appear_ts)
            skipped = 0
            for e in new_appearances:
                key = f"{e.device}|{e.fault}"
                if e.appear_ts < int(cooldown.get(key, 0)) + COOLDOWN_S * 1000:
                    skipped += 1
                    continue  # anti-rebond 6 h : pas de nouveau cycle
                # Une entree deja suivie est REARMEE, pas ignoree. Si on la
                # laissait en place, une entree restee bloquee (resolution
                # jamais observee, par exemple apres une coupure de cron plus
                # longue que LOOKBACK_MAX_S) avalerait silencieusement toutes
                # les apparitions suivantes de ce defaut : `fresh` exige
                # `mails == 0`, donc elles ne seraient JAMAIS notifiees. Le
                # cooldown 6 h ci-dessus est ce qui empeche un rearmement en
                # rafale. Un defaut normalement suivi ne repasse pas ici : son
                # apparition est derriere le curseur.
                tracked[key] = {"appear_ts": e.appear_ts, "mails": 0, "last_mail_ts": 0}
                cooldown[key] = e.appear_ts
            if skipped:
                log.info("device=%s %d apparition(s) dans le cooldown 6h", dev_name, skipped)

    # ── 2. Echeances : sursis ecoule -> mail d'apparition, ou rappel du ──
    grace_ms = mail_grace_ms()
    steps = common_reminder_steps()
    fresh = sorted(k for k, v in tracked.items()
                   if v["mails"] == 0 and now_ms - v["appear_ts"] >= grace_ms)
    due = sorted(k for k, v in tracked.items() if reminder_due(v, now_ms, steps))

    # Une cle illisible ne pourra JAMAIS etre notifiee. On la purge au lieu de
    # consommer son echeance : la consommer la ferait re-journaliser un
    # avertissement a chaque palier, indefiniment, sans jamais la faire sortir
    # de la memoire. Purger est strictement mieux que faire escalader quelque
    # chose qui ne partira jamais.
    bad = sorted(k for k in set(fresh) | set(due) if _synthetic(k, tracked[k]) is None)
    if bad:
        log.warning("device=%s cle(s) de memoire illisible(s), purgee(s): %s",
                    dev_name, ", ".join(bad))
        for key in bad:
            tracked.pop(key, None)
        fresh = [k for k in fresh if k not in set(bad)]
        due = [k for k in due if k not in set(bad)]

    if fresh or due:
        emails = tb.get_recipients_for_device(dev_id, users)
        display = attrs.get("nom_residence") or attrs.get("nom_alternatif") or dev_name
        addr = attrs.get("adresse") or ""
        if emails:
            _mail_batch(emails, dev_name, display, addr, tracked, fresh, now_ms, reminder=False)
            _mail_batch(emails, dev_name, display, addr, tracked, due, now_ms, reminder=True)
        else:
            log.info("device=%s %d apparition(s) / %d rappel(s) mais aucun destinataire",
                     dev_name, len(fresh), len(due))
        # Echeances consommees meme sans destinataire : sinon elles se
        # redeclencheraient a chaque run indefiniment (esprit de M18).
        for key in fresh + due:
            tracked[key]["mails"] += 1
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

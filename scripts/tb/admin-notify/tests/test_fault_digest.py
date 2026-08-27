"""I7 : un defaut ouvert depuis plus de LOOKBACK_DAYS (30j) ne doit plus
disparaitre du digest — memorise via l'attribut SERVER_SCOPE par device
`digest_open_faults` (meme mecanisme que le curseur/cooldown de
fault_notify : cf. fault_notify._load_cooldown / save_server_attrs).

I8 : une erreur HTTP sur UN device ne doit plus tuer la collecte du parc
entier — try/except par device, comme fault_notify.main().

I1 : le faux TBClient de ce fichier est REJOUABLE — lectures couplees aux
ecritures et fenetre de requete honoree — de sorte qu'un enchainement de runs
horaires soit observable de bout en bout (cf. `make_client` et la derniere
section)."""
import datetime as dt

import common
import fault_digest as fd

NOW = 1_700_000_000_000
DAY_MS = 86400 * 1000

DEV = {"id": {"id": "dev-1"}, "name": "Chaufferie 1"}
DEV_OK = {"id": {"id": "dev-ok"}, "name": "Chaufferie OK"}
DEV_BAD = {"id": {"id": "dev-bad"}, "name": "Chaufferie Bad"}

EVT_KEYS = ["evt_type", "evt_fault", "evt_device", "evt_status", "evt_date", "evt_time", "evt_id", "fault_src"]


def _ts_payload(events):
    """events: iterable of (ts, evt_type, fault, device)."""
    payload = {k: [] for k in EVT_KEYS}
    for ts, typ, fault, device in events:
        payload["evt_type"].append({"ts": ts, "value": typ})
        payload["evt_fault"].append({"ts": ts, "value": fault})
        payload["evt_device"].append({"ts": ts, "value": device})
        payload["evt_status"].append({"ts": ts, "value": 1})
        payload["evt_date"].append({"ts": ts, "value": "10/07/2026"})
        payload["evt_time"].append({"ts": ts, "value": "12:00:00"})
        payload["evt_id"].append({"ts": ts, "value": 1})
        payload["fault_src"].append({"ts": ts, "value": 0})
    return payload


def make_client(attrs_by_dev, ts_by_dev, raise_on=None):
    """TBClient reel, attrs/timeseries mockes par entite (device OU user).

    Deux proprietes rendent ce faux capable de rejouer une chronologie, ce
    que la premiere version ne savait pas faire (revue transverse I1) :

    - **les lectures voient les ecritures** : `_get_attrs` lit le meme dict que
      `_save_attrs` alimente. Sans ce couplage, aucun test ne pouvait faire
      dependre le `carried` d'un run de ce que le run precedent avait ecrit —
      or c'est TOUTE la semantique de `carried`, et c'est ce trou qui a laisse
      passer le defaut de fond de la branche rapide (C1). Meme forme que le
      harnais client, `tests/test_notify_cadence.py`.
    - **la fenetre de requete est honoree** : un run anterieur a l'apparition
      d'un defaut ne doit pas deja le voir, sinon la chronologie est fausse.

    `attrs_by_dev` est indexe par id d'entite : les etats d'utilisateur
    (`mail_digest_state`, via get_digest_state/save_digest_state) passent par
    le meme dict, ce qui rend `send_for_target` rejouable tel quel.
    raise_on = {"attrs": {dev_id, ...}, "ts": {dev_id, ...}} -> RuntimeError."""
    raise_on = raise_on or {}
    c = common.TBClient(url="http://test", user="svc", password="x")
    attrs = {eid: dict(v) for eid, v in (attrs_by_dev or {}).items()}
    saved: dict[str, dict] = {}

    def _get_attrs(etype, eid, keys=None):
        if eid in raise_on.get("attrs", ()):
            raise RuntimeError("network down")
        return dict(attrs.get(eid, {}))

    def _get_ts(dev_id, keys, start_ts, end_ts, limit=50000):
        if dev_id in raise_on.get("ts", ()):
            raise RuntimeError("network down")
        return {k: [p for p in pts if start_ts <= p["ts"] <= end_ts]
                for k, pts in ts_by_dev.get(dev_id, {}).items()}

    def _save_attrs(etype, eid, kv):
        attrs.setdefault(eid, {}).update(kv)
        saved.setdefault(eid, {}).update(kv)

    c.get_server_attrs = _get_attrs
    c.get_timeseries = _get_ts
    c.save_server_attrs = _save_attrs
    c.calls = {"save_server_attrs": saved}
    return c


# ─── I8 : isolation par device ──────────────────────────────────────────────

def test_device_error_isolated_others_still_collected():
    appear_ts = NOW - 1_000
    ts_by_dev = {"dev-ok": _ts_payload([(appear_ts, 1, 5, 1)])}
    c = make_client({}, ts_by_dev, raise_on={"ts": {"dev-bad"}})

    per, errors = fd.collect_open_per_device(c, [DEV_OK, DEV_BAD], NOW)

    assert errors == ["Chaufferie Bad"]
    assert len(per) == 1
    assert per[0]["name"] == "Chaufferie OK"
    assert len(per[0]["faults"]) == 1


def test_attrs_fetch_error_also_isolated():
    ts_by_dev = {"dev-ok": _ts_payload([(NOW - 1_000, 1, 5, 1)])}
    c = make_client({}, ts_by_dev, raise_on={"attrs": {"dev-bad"}})

    per, errors = fd.collect_open_per_device(c, [DEV_OK, DEV_BAD], NOW)

    assert errors == ["Chaufferie Bad"]
    assert len(per) == 1


def test_all_devices_erroring_still_returns_without_crash():
    c = make_client({}, {}, raise_on={"ts": {"dev-bad"}})
    per, errors = fd.collect_open_per_device(c, [DEV_BAD], NOW)
    assert per == []
    assert errors == ["Chaufferie Bad"]


# ─── I7 : memoire des defauts ouverts au-dela de la fenetre ─────────────────

def test_fault_older_than_window_carried_via_state():
    old_appear_ts = NOW - 40 * DAY_MS  # 40j > LOOKBACK_DAYS (30j)
    attrs = {"dev-1": {fd.STATE_ATTR: {"5|1": old_appear_ts}}}
    ts_by_dev = {"dev-1": _ts_payload([])}  # rien dans la fenetre de 30j
    c = make_client(attrs, ts_by_dev)

    per, errors = fd.collect_open_per_device(c, [DEV], NOW)

    assert errors == []
    assert len(per) == 1
    assert len(per[0]["faults"]) == 1
    e = per[0]["faults"][0]
    assert e.appear_ts == old_appear_ts
    assert e.fault == 5
    assert e.device == 1
    # l'etat est reconduit tel quel (toujours ouvert, pas de resolution vue)
    assert c.calls["save_server_attrs"]["dev-1"][fd.STATE_ATTR] == {"5|1": old_appear_ts}


def test_resolution_seen_in_window_clears_state_and_digest():
    old_appear_ts = NOW - 40 * DAY_MS
    resolved_ts = NOW - 1_000
    attrs = {"dev-1": {fd.STATE_ATTR: {"5|1": old_appear_ts}}}
    # resolution (type=4) seule dans la fenetre -> standalone, mais matche la cle memorisee
    ts_by_dev = {"dev-1": _ts_payload([(resolved_ts, 4, 5, 1)])}
    c = make_client(attrs, ts_by_dev)

    per, errors = fd.collect_open_per_device(c, [DEV], NOW)

    assert errors == []
    assert per == []  # plus aucun defaut ouvert pour ce device
    assert c.calls["save_server_attrs"]["dev-1"][fd.STATE_ATTR] == {}


def test_fresh_open_fault_in_window_is_persisted_to_state():
    appear_ts = NOW - 1_000
    ts_by_dev = {"dev-1": _ts_payload([(appear_ts, 1, 9, 3)])}
    c = make_client({}, ts_by_dev)

    per, errors = fd.collect_open_per_device(c, [DEV], NOW)

    assert errors == []
    assert len(per) == 1
    assert c.calls["save_server_attrs"]["dev-1"][fd.STATE_ATTR] == {"9|3": appear_ts}


def test_corrupted_state_value_starts_fresh_no_crash():
    appear_ts = NOW - 1_000
    attrs = {"dev-1": {fd.STATE_ATTR: "not-json-{{{"}}
    ts_by_dev = {"dev-1": _ts_payload([(appear_ts, 1, 7, 2)])}
    c = make_client(attrs, ts_by_dev)

    per, errors = fd.collect_open_per_device(c, [DEV], NOW)

    assert errors == []
    assert len(per) == 1
    assert per[0]["faults"][0].fault == 7


def test_corrupted_state_wrong_type_starts_fresh_no_crash():
    attrs = {"dev-1": {fd.STATE_ATTR: ["not", "a", "dict"]}}
    ts_by_dev = {"dev-1": _ts_payload([])}
    c = make_client(attrs, ts_by_dev)

    per, errors = fd.collect_open_per_device(c, [DEV], NOW)

    assert errors == []
    assert per == []  # pas de defaut du tout, aucun crash


def test_missing_state_attr_starts_fresh():
    ts_by_dev = {"dev-1": _ts_payload([])}
    c = make_client({"dev-1": {}}, ts_by_dev)
    per, errors = fd.collect_open_per_device(c, [DEV], NOW)
    assert errors == []
    assert per == []


def test_device_dropped_from_fleet_state_not_touched():
    """Documente la reponse a I7 (entrees obsoletes) : l'etat vit SUR le
    device (attribut SERVER_SCOPE), pas dans un blob partage — un device qui
    disparait de list_devices_by_profile n'est simplement plus visite, il
    n'y a donc rien a purger explicitement."""
    c = make_client({}, {})
    per, errors = fd.collect_open_per_device(c, [], NOW)
    assert per == []
    assert errors == []
    assert c.calls["save_server_attrs"] == {}


# ─── render / build : ne pas presenter une collecte partielle comme "propre" ─

def test_render_digest_mentions_erroring_devices():
    html, text = fd.render_digest([], NOW, errors=["Chaufferie Bad"])
    assert "Chaufferie Bad" in html
    assert "Chaufferie Bad" in text


def test_build_digest_none_when_nothing_open_and_no_errors():
    assert fd.build_digest([], [], NOW) is None


def test_build_digest_sent_when_only_errors_no_open_faults():
    # Pas de defaut ouvert connu, mais une collecte a echoue -> il ne faut
    # PAS envoyer "aucun defaut" en silence (donnee manquante != parc sain).
    built = fd.build_digest([], ["Chaufferie Bad"], NOW)
    assert built is not None
    subject, html, text = built
    assert "Chaufferie Bad" in html or "Chaufferie Bad" in subject


def test_build_digest_sent_when_faults_present():
    info = {"name": "d1", "display": "d1", "address": "", "faults": []}
    built = fd.build_digest([info], [], NOW)
    assert built is not None


# ── Task 4 : _process_device remonte l'id et la memoire precedente ──────────

def test_process_device_reports_id_and_empty_carried_for_fresh_fault():
    """Chaufferie saine au run precedent (pas de memoire) qui tombe en defaut :
    `carried` vide, donc l'episode n'est pas encore "etabli" au sens du
    quotidien (spec §4.1 condition 4). La candidature au mail RAPIDE, elle, ne
    se lit pas sur `carried` mais sur `appear_ts > last_mail_ts`."""
    c = make_client({"dev-1": {}},
                    {"dev-1": _ts_payload([(NOW - 3600_000, 1, 15, 50)])})
    info = fd._process_device(c, DEV, NOW - 30 * DAY_MS, NOW)
    assert info["id"] == "dev-1"
    assert info["carried"] == set()
    assert len(info["faults"]) == 1


def test_process_device_reports_carried_from_previous_run():
    """Defaut deja memorise et jamais resolu : `carried` non vide, l'episode a
    donc survecu a un run et le quotidien peut partir."""
    c = make_client({"dev-1": {fd.STATE_ATTR: {"15|50": NOW - 5 * DAY_MS}}},
                    {"dev-1": {}})
    info = fd._process_device(c, DEV, NOW - 30 * DAY_MS, NOW)
    assert info["carried"] == {"15|50"}
    assert info["id"] == "dev-1"


def test_process_device_carried_keeps_faults_resolved_this_run():
    """Un defaut memorise ET resolu ce run laisse quand meme une trace dans
    `carried` : la chaufferie etait bien en defaut au run precedent, l'episode
    compte donc comme etabli pour le quotidien."""
    c = make_client({"dev-1": {fd.STATE_ATTR: {"15|50": NOW - 5 * DAY_MS}}},
                    {"dev-1": _ts_payload([(NOW - 7200_000, 4, 15, 50),
                                           (NOW - 3600_000, 1, 16, 50)])})
    info = fd._process_device(c, DEV, NOW - 30 * DAY_MS, NOW)
    assert info["carried"] == {"15|50"}
    assert [e.fault for e in info["faults"]] == [16]


# ─── I1 : rejeu de plusieurs runs horaires a travers le vrai pipeline ───────
# Ce que le harnais d'origine ne permettait pas d'ecrire : des runs enchaines
# ou le `carried` d'un run provient de ce que le run precedent a REELLEMENT
# persiste. C'est a ce niveau, et pas sur `decide_mail` seule, que se voit le
# fonctionnement (ou non) de la branche rapide.

CADENCE_CFG = {"grace_ms": 60 * 60 * 1000, "recap_hour": 7,
               "min_gap_ms": 6 * 3600 * 1000, "fast_quota_ms": 24 * 3600 * 1000}
TARGET = {"id": "u1", "email": "a@yahtec.com", "exclude": set()}


def _at(day, hour, minute=0):
    """2026-08-<day> <hour>:<minute> heure LOCALE, en ms. L'ancre du quotidien
    est une heure locale : les horodatages doivent etre construits comme tels
    pour que le test passe quel que soit le fuseau de la machine."""
    return int(dt.datetime(2026, 8, day, hour, minute).timestamp() * 1000)


def _replay(c, hours, monkeypatch, target=None):
    """Joue un run de digest complet (collecte + cadence + envoi) par element
    de `hours`, et retourne la liste des (jour, heure, kind) envoyes."""
    target = dict(target or TARGET)
    sent = []
    monkeypatch.setattr(fd, "send_mail", lambda to, subject, html, text=None: None)
    for day, hour in hours:
        now = _at(day, hour)
        per, errors = fd.collect_open_per_device(c, [DEV], now)
        kind = fd.send_for_target(c, target, per, errors,
                                  {DEV["name"]: "dev-1"}, now, CADENCE_CFG)
        if kind:
            sent.append((day, hour, kind))
    return sent


def test_a_fault_born_after_the_recap_gets_its_fast_mail_end_to_end(monkeypatch):
    """Regression du defaut principal de la revue transverse (C1), prouvee sur
    le vrai pipeline : un defaut apparu a 06 h 10 doit partir en mail RAPIDE au
    run de 08 h — premier run ou son sursis d'une heure est ecoule — et non
    attendre le quotidien du lendemain 7 h. Au run de 08 h la memoire du device
    est deja ecrite (run de 07 h), donc `carried` est non vide : c'est
    exactement la situation ou l'ancienne regle rendait cette branche
    inatteignable."""
    c = make_client({}, {"dev-1": _ts_payload([(_at(10, 6, 10), 1, 15, 50)])})
    hours = [(10, h) for h in range(5, 24)] + [(11, h) for h in range(0, 9)]
    assert _replay(c, hours, monkeypatch) == [(10, 8, "fast"), (11, 7, "daily")]


def test_at_most_two_mails_per_calendar_day_over_24_hourly_runs(monkeypatch):
    """Le plafond que l'utilisateur a valide, verifie comme tel : au plus DEUX
    mails par jour calendaire et par destinataire — un quotidien plus au plus
    un rapide — malgre 24 runs horaires. Mise en scene : un defaut deja ouvert
    depuis la veille (episode etabli, quotidien du a 7 h) et un second defaut
    qui apparait a 09 h 10 (candidat rapide, quota libre)."""
    c = make_client({"dev-1": {fd.STATE_ATTR: {"15|50": _at(9, 20)}},
                     "u1": {common.DIGEST_STATE_ATTR: {
                         "last_mail_ts": _at(9, 21), "last_fast_ts": _at(9, 8)}}},
                    {"dev-1": _ts_payload([(_at(10, 9, 10), 1, 16, 50)])})
    sent = _replay(c, [(10, h) for h in range(24)], monkeypatch)
    assert sent == [(10, 7, "daily"), (10, 11, "fast")]


def test_a_transient_fault_produces_no_mail_at_all_end_to_end(monkeypatch):
    """Contrepartie : le sursis doit tenir sur le pipeline complet. Un defaut
    apparu a 09 h 10 et resolu a 09 h 40 traverse deux runs horaires sans
    jamais produire de mail, et la memoire du device se vide."""
    c = make_client({}, {"dev-1": _ts_payload([(_at(10, 9, 10), 1, 15, 50),
                                               (_at(10, 9, 40), 4, 15, 50)])})
    assert _replay(c, [(10, h) for h in range(8, 24)], monkeypatch) == []
    assert c.calls["save_server_attrs"]["dev-1"][fd.STATE_ATTR] == {}

"""I7 : un defaut ouvert depuis plus de LOOKBACK_DAYS (30j) ne doit plus
disparaitre du digest — memorise via l'attribut SERVER_SCOPE par device
`digest_open_faults` (meme mecanisme que le curseur/cooldown de
fault_notify : cf. fault_notify._load_cooldown / save_server_attrs).

I8 : une erreur HTTP sur UN device ne doit plus tuer la collecte du parc
entier — try/except par device, comme fault_notify.main()."""
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
    """TBClient reel, attrs/timeseries mockes par device id.
    raise_on = {"attrs": {dev_id, ...}, "ts": {dev_id, ...}} -> RuntimeError."""
    raise_on = raise_on or {}
    c = common.TBClient(url="http://test", user="svc", password="x")
    saved: dict[str, dict] = {}

    def _get_attrs(etype, eid, keys=None):
        if eid in raise_on.get("attrs", ()):
            raise RuntimeError("network down")
        return dict(attrs_by_dev.get(eid, {}))

    def _get_ts(dev_id, keys, start_ts, end_ts, limit=50000):
        if dev_id in raise_on.get("ts", ()):
            raise RuntimeError("network down")
        return ts_by_dev.get(dev_id, {})

    def _save_attrs(etype, eid, kv):
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
    `carried` vide, c'est ce qui la rend candidate au mail rapide."""
    c = make_client({"dev-1": {}},
                    {"dev-1": _ts_payload([(NOW - 3600_000, 1, 15, 50)])})
    info = fd._process_device(c, DEV, NOW - 30 * DAY_MS, NOW)
    assert info["id"] == "dev-1"
    assert info["carried"] == set()
    assert len(info["faults"]) == 1


def test_process_device_reports_carried_from_previous_run():
    """Defaut deja memorise et jamais resolu : `carried` non vide, la
    chaufferie n'est donc pas "nouvellement en defaut"."""
    c = make_client({"dev-1": {fd.STATE_ATTR: {"15|50": NOW - 5 * DAY_MS}}},
                    {"dev-1": {}})
    info = fd._process_device(c, DEV, NOW - 30 * DAY_MS, NOW)
    assert info["carried"] == {"15|50"}
    assert info["id"] == "dev-1"


def test_process_device_carried_keeps_faults_resolved_this_run():
    """Un defaut memorise ET resolu ce run laisse quand meme une trace dans
    `carried` : la chaufferie etait bien en defaut au run precedent, donc un
    nouveau defaut apparu en meme temps ne doit pas passer pour une entree en
    defaut depuis un etat sain."""
    c = make_client({"dev-1": {fd.STATE_ATTR: {"15|50": NOW - 5 * DAY_MS}}},
                    {"dev-1": _ts_payload([(NOW - 7200_000, 4, 15, 50),
                                           (NOW - 3600_000, 1, 16, 50)])})
    info = fd._process_device(c, DEV, NOW - 30 * DAY_MS, NOW)
    assert info["carried"] == {"15|50"}
    assert [e.fault for e in info["faults"]] == [16]

"""Machine a etats du recap admin (spec §4.1). Fonction pure : tout le temps
entre par now_ms, aucun reseau, aucune horloge reelle.

Les horodatages sont construits depuis des datetimes LOCALES (`_at`) et non
depuis des constantes epoch : l'ancre quotidienne est une heure locale, les
tests doivent donc passer quel que soit le fuseau de la machine."""
import datetime as dt

import common
import fault_digest as fd

H = 3600 * 1000
CFG = {"grace_ms": 60 * 60 * 1000, "recap_hour": 7,
       "min_gap_ms": 6 * H, "fast_quota_ms": 24 * H}


def _at(day, hour, minute=0):
    """2026-08-<day> <hour>:<minute> heure locale, en ms."""
    return int(dt.datetime(2026, 8, day, hour, minute).timestamp() * 1000)


def _info(dev_id, appear_ts, carried=()):
    """Une chaufferie en defaut telle que la rend _process_device."""
    ev = common.Event(ts=appear_ts, appear_ts=appear_ts, type=1, fault=15,
                      device=50, status=0, fault_src=-1, evt_id=0)
    return {"id": dev_id, "name": dev_id, "display": dev_id, "address": "",
            "faults": [ev], "carried": set(carried)}


def _state(last_mail=0, last_fast=0):
    return {"last_mail_ts": last_mail, "last_fast_ts": last_fast}


# ── Perimetre sain ──────────────────────────────────────────────────────────

def test_clean_perimeter_sends_nothing_and_closes_episode():
    kind, st = fd.decide_mail([], _state(last_mail=_at(10, 7), last_fast=_at(10, 7)),
                              _at(10, 12), CFG)
    assert kind is None
    assert st["last_mail_ts"] == 0                      # episode clos
    assert st["last_fast_ts"] == _at(10, 7)             # limiteur conserve


# ── Mail rapide ─────────────────────────────────────────────────────────────

def test_no_fast_mail_before_grace_elapsed():
    kind, st = fd.decide_mail([_info("d1", _at(10, 14, 30))], _state(), _at(10, 15), CFG)
    assert kind is None
    assert st == _state()


def test_fast_mail_once_grace_elapsed():
    kind, st = fd.decide_mail([_info("d1", _at(10, 14))], _state(), _at(10, 15), CFG)
    assert kind == "fast"
    assert st == _state(last_mail=_at(10, 15), last_fast=_at(10, 15))


def test_device_already_open_last_run_is_not_a_fast_candidate():
    """Deuxieme defaut sur une chaufferie deja en defaut : pas de mail rapide."""
    kind, _ = fd.decide_mail([_info("d1", _at(10, 14), carried={"15|50"})],
                             _state(last_mail=_at(10, 7)), _at(10, 15), CFG)
    assert kind is None


def test_second_site_falling_triggers_fast_mail_mid_episode():
    """Une chaufferie deja en defaut n'aveugle pas sur une nouvelle."""
    per = [_info("d1", _at(7, 9), carried={"15|50"}), _info("d2", _at(10, 14))]
    kind, _ = fd.decide_mail(per, _state(last_mail=_at(10, 7)), _at(10, 15), CFG)
    assert kind == "fast"


def test_fast_quota_blocks_a_second_fast_mail_the_same_day():
    """Troisieme site qui tombe le meme jour : quota consomme, il attendra."""
    kind, st = fd.decide_mail([_info("d3", _at(10, 17))],
                              _state(last_mail=_at(10, 15), last_fast=_at(10, 15)),
                              _at(10, 18), CFG)
    assert kind is None
    assert st == _state(last_mail=_at(10, 15), last_fast=_at(10, 15))


def test_fast_quota_frees_after_24h():
    kind, _ = fd.decide_mail([_info("d3", _at(11, 17))],
                             _state(last_mail=_at(10, 15), last_fast=_at(10, 15)),
                             _at(11, 18), CFG)
    assert kind == "fast"


# ── Quotidien ancre ─────────────────────────────────────────────────────────

def test_daily_fires_at_anchor_for_an_established_episode():
    kind, st = fd.decide_mail([_info("d1", _at(9, 20), carried={"15|50"})],
                              _state(last_mail=_at(9, 21)), _at(10, 7), CFG)
    assert kind == "daily"
    assert st["last_mail_ts"] == _at(10, 7)


def test_daily_fires_only_once_despite_hourly_runs():
    """24 runs horaires dans la journee, un seul quotidien."""
    per = [_info("d1", _at(9, 20), carried={"15|50"})]
    st = _state(last_mail=_at(9, 21))
    sent = []
    for hour in range(24):
        kind, st = fd.decide_mail(per, st, _at(10, hour), CFG)
        if kind:
            sent.append((hour, kind))
    assert sent == [(7, "daily")]


def test_daily_does_not_drift_over_several_days():
    """Sur cinq jours, le quotidien reste a 7 h et ne glisse pas."""
    per = [_info("d1", _at(9, 20), carried={"15|50"})]
    st = _state(last_mail=_at(9, 21))
    hours = []
    for day in range(10, 15):
        for hour in range(24):
            kind, st = fd.decide_mail(per, st, _at(day, hour), CFG)
            if kind:
                hours.append(hour)
    assert hours == [7, 7, 7, 7, 7]


def test_daily_suppressed_when_a_fast_mail_just_went_out():
    """Rapide a 6 h 30, quotidien de 7 h supprime par l'ecart minimal."""
    per = [_info("d1", _at(10, 5), carried={"15|50"})]
    kind, _ = fd.decide_mail(per, _state(last_mail=_at(10, 6, 30), last_fast=_at(10, 6, 30)),
                             _at(10, 7), CFG)
    assert kind is None


def test_brand_new_episode_after_anchor_waits_for_grace_not_the_anchor():
    """Sans la garde "episode etabli", ce cas enverrait un mail des 14 h
    puisque l'ancre de 7 h est passee et last_mail vaut 0."""
    kind, _ = fd.decide_mail([_info("d1", _at(10, 14))], _state(), _at(10, 14, 5), CFG)
    assert kind is None


def test_episode_blocked_by_quota_is_announced_by_the_daily_branch():
    """Rapide bloque par le quota, mais l'episode a survecu a un run : la
    branche quotidienne l'annonce sans attendre le lendemain."""
    per = [_info("d2", _at(10, 16), carried={"15|50"})]
    kind, _ = fd.decide_mail(per, _state(last_mail=0, last_fast=_at(10, 15)),
                             _at(10, 18), CFG)
    assert kind == "daily"


# ── Invariant I8 : echec de collecte ────────────────────────────────────────

def test_collection_error_alone_still_reaches_the_daily():
    """Une panne de collecte ne doit jamais passer pour un parc sain."""
    kind, st = fd.decide_mail([], _state(last_mail=_at(9, 7)), _at(10, 7), CFG,
                              has_errors=True)
    assert kind == "daily"
    assert st["last_mail_ts"] == _at(10, 7)


def test_collection_error_never_triggers_a_fast_mail():
    kind, _ = fd.decide_mail([], _state(), _at(10, 3), CFG, has_errors=True)
    assert kind is None


# ── Ancre ───────────────────────────────────────────────────────────────────

def test_local_anchor_is_today_at_the_configured_hour():
    assert fd._local_anchor_ms(_at(10, 23, 59), 7) == _at(10, 7)
    assert fd._local_anchor_ms(_at(10, 0, 1), 7) == _at(10, 7)

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

def test_clean_perimeter_sends_nothing_and_keeps_both_limiters():
    """Les deux horodatages survivent a la fin d'un episode : ce sont des
    limiteurs de debit, pas des etats d'episode."""
    kind, st = fd.decide_mail([], _state(last_mail=_at(10, 7), last_fast=_at(10, 7)),
                              _at(10, 12), CFG)
    assert kind is None
    assert st == _state(last_mail=_at(10, 7), last_fast=_at(10, 7))


def test_resolved_then_refaulted_same_day_gets_no_second_daily():
    """Le cas qui casserait le plafond de 2 mails/jour si la fin d'episode
    remettait last_mail_ts a 0 : les deux freins du quotidien lisent cet
    horodatage, les liberer ferait repartir un recap toutes les 3 heures."""
    # `last_fast` pose au meme instant que `last_mail` : le quota rapide est
    # consomme, ce qui isole ce que ce test veut prouver — l'absence d'un SECOND
    # quotidien. Le rapide, lui, a son propre test.
    st = _state(last_mail=_at(10, 10), last_fast=_at(10, 10))
    # 11h : le defaut se resout, perimetre sain
    kind, st = fd.decide_mail([], st, _at(10, 11), CFG)
    assert kind is None
    # 12h : nouveau defaut apparu a 11h30, sursis non ecoule, pas encore memorise
    kind, st = fd.decide_mail([_info("d1", _at(10, 11, 30))], st, _at(10, 12), CFG)
    assert kind is None
    # 13h : l'episode a survecu a un run, il est donc "etabli" — mais le
    # quotidien est deja parti a 10h aujourd'hui, il ne doit PAS repartir
    kind, _ = fd.decide_mail([_info("d1", _at(10, 11, 30), carried={"15|50"})],
                             st, _at(10, 13), CFG)
    assert kind is None


def test_new_episode_the_day_after_still_gets_its_daily():
    """Contrepartie du test precedent : conserver last_mail_ts ne baillonne pas
    un episode du lendemain, puisqu'un horodatage de la veille est bien
    inferieur a l'ancre du jour.

    `last_fast` pose au meme instant que `last_mail` (donc quota rapide encore
    consomme a 7 h le lendemain) pour la meme raison que dans le test
    precedent : c'est la branche QUOTIDIENNE qu'il s'agit d'isoler. Un defaut
    apparu apres le dernier mail est desormais candidat au rapide (spec §4.1),
    qui gagnerait sinon la main."""
    kind, _ = fd.decide_mail([_info("d1", _at(11, 5), carried={"15|50"})],
                             _state(last_mail=_at(10, 10), last_fast=_at(10, 10)),
                             _at(11, 7), CFG)
    assert kind == "daily"


# ── Mail rapide ─────────────────────────────────────────────────────────────

def test_no_fast_mail_before_grace_elapsed():
    kind, st = fd.decide_mail([_info("d1", _at(10, 14, 30))], _state(), _at(10, 15), CFG)
    assert kind is None
    assert st == _state()


def test_fast_mail_once_grace_elapsed():
    kind, st = fd.decide_mail([_info("d1", _at(10, 14))], _state(), _at(10, 15), CFG)
    assert kind == "fast"
    assert st == _state(last_mail=_at(10, 15), last_fast=_at(10, 15))


def test_fault_already_covered_by_a_mail_is_not_a_fast_candidate():
    """Un defaut dont l'apparition PRECEDE le dernier mail a deja ete annonce a
    ce destinataire : il ne doit pas redeclencher un rapide."""
    kind, _ = fd.decide_mail([_info("d1", _at(10, 5), carried={"15|50"})],
                             _state(last_mail=_at(10, 7)), _at(10, 15), CFG)
    assert kind is None


def test_fast_fires_for_a_fault_born_after_the_days_recap():
    """Regression du defaut principal trouve en revue transverse : la branche
    rapide etait inatteignable parce qu'elle exigeait une chaufferie "sans
    memoire au run precedent", condition incompatible avec un sursis d'une
    heure et un cron horaire. Un defaut apparu apres le recap du jour doit
    partir a T+1h, pas attendre le lendemain 7 h."""
    per = [_info("d1", _at(10, 9, 10), carried={"15|50"})]
    kind, st = fd.decide_mail(per, _state(last_mail=_at(10, 7), last_fast=_at(9, 8)),
                              _at(10, 11), CFG)
    assert kind == "fast"
    assert st == _state(last_mail=_at(10, 11), last_fast=_at(10, 11))


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


def test_fast_quota_boundary_is_inclusive():
    """Exactement 24 h depuis le dernier rapide : la borne doit passer."""
    kind, _ = fd.decide_mail([_info("d1", _at(11, 13))],
                             _state(last_mail=_at(10, 15), last_fast=_at(10, 15)),
                             _at(11, 15), CFG)
    assert kind == "fast"


def test_fast_candidate_blocked_by_quota_falls_through_to_the_daily():
    """La combinaison reelle : candidat rapide (sursis ecoule, jamais vu au run
    precedent) PLUS quota consomme PLUS episode etabli par une autre
    chaufferie. Sans ce cas, retirer la condition de quota ne ferait echouer
    aucun test."""
    per = [_info("d1", _at(10, 5), carried={"15|50"}),   # etablit l'episode
           _info("d2", _at(10, 16))]                     # candidat rapide
    kind, _ = fd.decide_mail(per, _state(last_mail=0, last_fast=_at(10, 15)),
                             _at(10, 18), CFG)
    assert kind == "daily"


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


def test_daily_still_goes_out_later_the_same_day_after_a_fast():
    """Contrepartie : l'ecart minimal decale le quotidien, il ne l'annule pas.
    « n'envoie plus rien pendant des jours » est le mode de defaillance a
    exclure, il faut donc verifier la reprise et pas seulement la suppression."""
    per = [_info("d1", _at(10, 5), carried={"15|50"})]
    kind, _ = fd.decide_mail(per, _state(last_mail=_at(10, 6, 30), last_fast=_at(10, 6, 30)),
                             _at(10, 13), CFG)
    assert kind == "daily"


def test_min_gap_boundary_is_inclusive():
    """Exactement 6 h depuis le dernier mail : la borne doit passer."""
    kind, _ = fd.decide_mail([_info("d1", _at(10, 1), carried={"15|50"})],
                             _state(last_mail=_at(10, 2)), _at(10, 8), CFG)
    assert kind == "daily"


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

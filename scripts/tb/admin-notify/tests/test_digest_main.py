"""main() du digest : un envoi par destinataire, filtre par ses exclusions,
etat persiste par utilisateur (spec §4.1, §6.2, §7)."""
import datetime as dt

import common
import fault_digest as fd

H = 3600 * 1000
CFG = {"grace_ms": 60 * 60 * 1000, "recap_hour": 7,
       "min_gap_ms": 6 * H, "fast_quota_ms": 24 * H}


def _at(day, hour, minute=0):
    return int(dt.datetime(2026, 8, day, hour, minute).timestamp() * 1000)


def _info(dev_id, name, appear_ts, carried=()):
    ev = common.Event(ts=appear_ts, appear_ts=appear_ts, type=1, fault=15,
                      device=50, status=0, fault_src=-1, evt_id=0)
    return {"id": dev_id, "name": name, "display": name, "address": "",
            "faults": [ev], "carried": set(carried)}


class FakeTB:
    def __init__(self, states=None):
        self.states = dict(states or {})
        self.saved = []

    def get_digest_state(self, uid):
        return common.load_digest_state(self.states.get(uid))

    def save_digest_state(self, uid, state):
        self.states[uid] = dict(state)
        self.saved.append((uid, dict(state)))


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(fd, "send_mail",
                        lambda to, subject, html, text=None: sent.append((to, subject, text)))
    return sent


def test_recipient_only_sees_his_own_perimeter(monkeypatch):
    sent = _capture(monkeypatch)
    tb = FakeTB()
    per = [_info("d1", "111", _at(9, 20), carried={"15|50"}),
           _info("d2", "222", _at(9, 20), carried={"15|50"})]
    target = {"id": "u1", "email": "a@yahtec.com", "exclude": {"d2"}}
    kind = fd.send_for_target(tb, target, per, [], {"111": "d1", "222": "d2"},
                              _at(10, 7), CFG)
    assert kind == "daily"
    assert sent[0][0] == ["a@yahtec.com"]
    assert "111" in sent[0][2] and "222" not in sent[0][2]


def test_recipient_with_empty_perimeter_gets_nothing_and_keeps_his_limiters(monkeypatch):
    """La seule chaufferie en defaut est hors de son perimetre : silence, et
    ses deux limiteurs de debit sont conserves tels quels."""
    sent = _capture(monkeypatch)
    tb = FakeTB({"u1": {"last_mail_ts": _at(9, 7), "last_fast_ts": _at(9, 7)}})
    per = [_info("d2", "222", _at(9, 20), carried={"15|50"})]
    target = {"id": "u1", "email": "a@yahtec.com", "exclude": {"d2"}}
    assert fd.send_for_target(tb, target, per, [], {"222": "d2"}, _at(10, 7), CFG) is None
    assert sent == []
    assert tb.states["u1"] == {"last_mail_ts": _at(9, 7), "last_fast_ts": _at(9, 7)}


def test_collection_errors_are_filtered_by_perimeter(monkeypatch):
    """Inutile de signaler a ce destinataire une panne sur une chaufferie
    qu'il ne suit pas."""
    sent = _capture(monkeypatch)
    tb = FakeTB()
    target = {"id": "u1", "email": "a@yahtec.com", "exclude": {"d2"}}
    assert fd.send_for_target(tb, target, [], ["222"], {"222": "d2"},
                              _at(10, 7), CFG) is None
    assert sent == []


def test_collection_error_inside_perimeter_still_sends(monkeypatch):
    sent = _capture(monkeypatch)
    tb = FakeTB({"u1": {"last_mail_ts": _at(9, 7), "last_fast_ts": 0}})
    target = {"id": "u1", "email": "a@yahtec.com", "exclude": set()}
    assert fd.send_for_target(tb, target, [], ["222"], {"222": "d2"},
                              _at(10, 7), CFG) == "daily"
    assert "222" in sent[0][2]


def test_state_is_persisted_even_when_nothing_is_sent(monkeypatch):
    _capture(monkeypatch)
    tb = FakeTB()
    target = {"id": "u1", "email": "a@yahtec.com", "exclude": set()}
    fd.send_for_target(tb, target, [], [], {}, _at(10, 7), CFG)
    assert tb.saved == [("u1", {"last_mail_ts": 0, "last_fast_ts": 0})]


def test_two_recipients_with_different_exclusions_get_different_content(monkeypatch):
    sent = _capture(monkeypatch)
    tb = FakeTB()
    per = [_info("d1", "111", _at(9, 20), carried={"15|50"}),
           _info("d2", "222", _at(9, 20), carried={"15|50"})]
    ids = {"111": "d1", "222": "d2"}
    fd.send_for_target(tb, {"id": "u1", "email": "a@yahtec.com", "exclude": set()},
                       per, [], ids, _at(10, 7), CFG)
    fd.send_for_target(tb, {"id": "u2", "email": "b@yahtec.com", "exclude": {"d2"}},
                       per, [], ids, _at(10, 7), CFG)
    bodies = {to[0]: text for to, _subject, text in sent}
    assert "222" in bodies["a@yahtec.com"]
    assert "222" not in bodies["b@yahtec.com"]


# ── Repli quand TB ne rend aucun admin ──────────────────────────────────────

def test_fallback_sends_only_at_the_anchor_hour(monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setenv("PARC_ADMINS_FALLBACK", "secours@yahtec.com")
    per = [_info("d1", "111", _at(9, 20), carried={"15|50"})]
    assert fd.fallback_daily(per, [], _at(10, 12)) == 0
    assert sent == []
    assert fd.fallback_daily(per, [], _at(10, 7)) == 0
    assert sent[0][0] == ["secours@yahtec.com"]


def test_fallback_without_addresses_returns_error_code(monkeypatch):
    _capture(monkeypatch)
    monkeypatch.setenv("PARC_ADMINS_FALLBACK", "")
    assert fd.fallback_daily([], [], _at(10, 7)) == 2

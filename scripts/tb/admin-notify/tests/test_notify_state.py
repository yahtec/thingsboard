"""Parseur d'attribut d'etat + mute global (spec §5.3 et §6.1)."""
import common


def test_load_state_attr_accepts_dict_and_json_string():
    assert common.load_state_attr({"a": 1}) == {"a": 1}
    assert common.load_state_attr('{"a": 1}') == {"a": 1}


def test_load_state_attr_treats_garbage_as_empty():
    for raw in (None, "", "pas du json", "[1,2]", 42, [], '"chaine"'):
        assert common.load_state_attr(raw) == {}, raw


def test_load_int_map_coerces_and_skips_bad_entries():
    assert common.load_int_map({"a": "12", "b": 3, "c": None, "d": "x"}) == {"a": 12, "b": 3}


def test_load_int_map_on_garbage_is_empty():
    assert common.load_int_map("nope") == {}


def test_excluded_device_names_defaults_to_test_bench(monkeypatch):
    monkeypatch.delenv("NOTIFY_EXCLUDE_DEVICES", raising=False)
    assert common.excluded_device_names() == {"2610000001"}


def test_excluded_device_names_reads_env_and_trims(monkeypatch):
    monkeypatch.setenv("NOTIFY_EXCLUDE_DEVICES", " 111 , 222 ,, ")
    assert common.excluded_device_names() == {"111", "222"}


def test_excluded_device_names_empty_env_excludes_nothing(monkeypatch):
    monkeypatch.setenv("NOTIFY_EXCLUDE_DEVICES", "")
    assert common.excluded_device_names() == set()


def test_filter_excluded_reports_what_it_dropped():
    devices = [{"name": "111"}, {"name": "222"}, {"name": "333"}]
    kept, dropped = common.filter_excluded(devices, {"222"})
    assert [d["name"] for d in kept] == ["111", "333"]
    assert dropped == ["222"]


# ── Reglages de cadence (spec §8) ───────────────────────────────────────────

H = 3600 * 1000


def test_cadence_defaults(monkeypatch):
    for name in ("MAIL_GRACE_MIN", "DIGEST_RECAP_HOUR", "DIGEST_MIN_GAP_HOURS",
                 "DIGEST_FAST_QUOTA_HOURS", "NOTIFY_REMINDER_HOURS"):
        monkeypatch.delenv(name, raising=False)
    assert common.mail_grace_ms() == 60 * 60 * 1000
    assert common.digest_recap_hour() == 7
    assert common.digest_min_gap_ms() == 6 * H
    assert common.digest_fast_quota_ms() == 24 * H
    assert common.reminder_steps_ms() == [24 * H, 72 * H, 168 * H]


def test_cadence_reads_env(monkeypatch):
    monkeypatch.setenv("MAIL_GRACE_MIN", "15")
    monkeypatch.setenv("DIGEST_RECAP_HOUR", "9")
    monkeypatch.setenv("NOTIFY_REMINDER_HOURS", "1, 2 ,3")
    assert common.mail_grace_ms() == 15 * 60 * 1000
    assert common.digest_recap_hour() == 9
    assert common.reminder_steps_ms() == [1 * H, 2 * H, 3 * H]


def test_cadence_falls_back_on_unparsable_env(monkeypatch):
    monkeypatch.setenv("MAIL_GRACE_MIN", "beaucoup")
    monkeypatch.setenv("DIGEST_RECAP_HOUR", "")
    assert common.mail_grace_ms() == 60 * 60 * 1000
    assert common.digest_recap_hour() == 7


def test_reminder_steps_skips_bad_entries_and_never_returns_empty(monkeypatch):
    monkeypatch.setenv("NOTIFY_REMINDER_HOURS", "12,zzz,48")
    assert common.reminder_steps_ms() == [12 * H, 48 * H]
    monkeypatch.setenv("NOTIFY_REMINDER_HOURS", "zzz,,")
    assert common.reminder_steps_ms() == [24 * H, 72 * H, 168 * H]

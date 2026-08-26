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

"""Tests unitaires de dash_cleanup_lib : detecteurs purs sur une config synthetique."""
import copy

import dash_cleanup_lib as lib

# Config synthetique exercant tous les detecteurs :
#  - w-placed  : place dans le state 'menu'
#  - w-orphan  : defini mais dans aucun layout      -> orphelin
#  - w-wip     : fqn contient 'wip'                 -> wip
#  - w-datakeys: place dans 'page', 2 dataKeys, ref alias 'a-used'
#  - a-used    : reference par w-datakeys           -> vivant
#  - a-dead    : reference nulle part               -> mort
CFG = {
    "widgets": {
        "w-placed":   {"typeFullFqn": "system.cards.html_card",    "config": {"title": "Placed"}},
        "w-orphan":   {"typeFullFqn": "system.cards.markdown_card","config": {"title": "Orphan"}},
        "w-wip":      {"typeFullFqn": "tenant.tsmart.pac_detail_top_wip", "config": {"title": "Detail"}},
        "w-datakeys": {"typeFullFqn": "tenant.tsmart.pac_chart",   "config": {"title": "Chart",
            "datasources": [{"entityAliasId": "a-used",
                             "dataKeys": [{"name": "pac_v2", "type": "timeseries"},
                                          {"name": "old_key", "type": "timeseries"}]}]}},
    },
    "states": {
        "menu": {"name": "Menu", "root": True,
                 "layouts": {"main": {"widgets": {"w-placed": {"row": 0}}}}},
        "page": {"name": "Page",
                 "layouts": {"main": {"widgets": {"w-wip": {"row": 0}, "w-datakeys": {"row": 1}}}}},
    },
    "entityAliases": {
        "a-used": {"alias": "Used", "filter": {"type": "stateEntity", "entityAliasId": None}},
        "a-dead": {"alias": "Dead", "filter": {"type": "deviceType"}},
    },
}


def test_get_config_unwraps_configuration():
    assert lib.get_config({"configuration": {"widgets": {}}}) == {"widgets": {}}
    assert lib.get_config({"widgets": {}}) == {"widgets": {}}
    assert lib.get_config(None) == {}


def test_placed_widget_ids():
    assert lib.placed_widget_ids(CFG) == {"w-placed", "w-wip", "w-datakeys"}


def test_find_orphan_widgets():
    assert lib.find_orphan_widgets(CFG) == ["w-orphan"]


def test_find_dead_aliases():
    assert lib.find_dead_aliases(CFG) == ["a-dead"]


def test_find_wip_widgets():
    wip = lib.find_wip_widgets(CFG)
    assert [w["id"] for w in wip] == ["w-wip"]
    assert wip[0]["fqn"] == "tenant.tsmart.pac_detail_top_wip"


def test_list_states_counts_widgets():
    states = lib.list_states(CFG)
    by_id = {s["id"]: s for s in states}
    assert by_id["menu"]["root"] is True and by_id["menu"]["widget_count"] == 1
    assert by_id["page"]["root"] is False and by_id["page"]["widget_count"] == 2


def test_list_datakeys():
    dk = lib.list_datakeys(CFG)
    names = sorted(d["key_name"] for d in dk)
    assert names == ["old_key", "pac_v2"]


def test_classify():
    assert lib.classify("Mes Installations") == "prod"
    assert lib.classify("Supervision flotte") == "prod"
    assert lib.classify("tests") == "nonprod"
    assert lib.classify("unite_backup") == "nonprod"
    assert lib.classify("Mes Installations – TSmart WIP") == "nonprod"


def test_detectors_do_not_mutate_input():
    before = copy.deepcopy(CFG)
    lib.find_orphan_widgets(CFG); lib.find_dead_aliases(CFG); lib.list_datakeys(CFG)
    assert CFG == before

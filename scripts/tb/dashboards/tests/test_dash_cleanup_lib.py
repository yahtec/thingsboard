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


# ---------- remove_items ----------

def test_remove_widget_purges_definition_and_layout():
    out = lib.remove_items(CFG, remove_widgets=["w-wip"])
    assert "w-wip" not in out["widgets"]
    assert "w-wip" not in out["states"]["page"]["layouts"]["main"]["widgets"]
    # les autres widgets restent
    assert "w-datakeys" in out["states"]["page"]["layouts"]["main"]["widgets"]


def test_remove_orphan_widget_only_touches_definition():
    out = lib.remove_items(CFG, remove_widgets=["w-orphan"])
    assert "w-orphan" not in out["widgets"]
    assert set(out["states"]["menu"]["layouts"]["main"]["widgets"]) == {"w-placed"}


def test_remove_alias():
    out = lib.remove_items(CFG, remove_aliases=["a-dead"])
    assert "a-dead" not in out["entityAliases"]
    assert "a-used" in out["entityAliases"]


def test_remove_state_drops_state_key():
    out = lib.remove_items(CFG, remove_states=["page"])
    assert "page" not in out["states"]
    assert "menu" in out["states"]


def test_remove_items_does_not_mutate_input():
    before = copy.deepcopy(CFG)
    lib.remove_items(CFG, remove_widgets=["w-wip"], remove_aliases=["a-dead"], remove_states=["page"])
    assert CFG == before


def test_remove_unknown_ids_is_noop():
    out = lib.remove_items(CFG, remove_widgets=["ghost"], remove_aliases=["ghost"], remove_states=["ghost"])
    assert out["widgets"].keys() == CFG["widgets"].keys()
    assert out["entityAliases"].keys() == CFG["entityAliases"].keys()
    assert out["states"].keys() == CFG["states"].keys()


# ---------- assemblage ----------

META = {"id": {"id": "dash-1"}, "title": "Mes Installations"}
FULL = {"id": {"id": "dash-1"}, "title": "Mes Installations", "version": 372, "configuration": CFG}
META_NP = {"id": {"id": "dash-2"}, "title": "unite_backup"}
FULL_NP = {"id": {"id": "dash-2"}, "title": "unite_backup", "version": 2, "configuration": CFG}


def test_audit_dashboard_shape():
    a = lib.audit_dashboard(META, FULL)
    assert a["id"] == "dash-1" and a["title"] == "Mes Installations" and a["version"] == 372
    assert a["classification"] == "prod"
    assert a["counts"] == {"widgets": 4, "states": 2, "aliases": 2}
    assert a["orphan_widgets"] == ["w-orphan"]
    assert a["dead_aliases"] == ["a-dead"]
    assert [w["id"] for w in a["wip_widgets"]] == ["w-wip"]


def test_build_decisions_prefills_clean_and_delete():
    audits = [lib.audit_dashboard(META, FULL), lib.audit_dashboard(META_NP, FULL_NP)]
    dec = lib.build_decisions(audits, "2026-07-17T10:00:00")
    assert dec["reviewed"] is False
    assert dec["dashboards"]["dash-2"]["action"] == "delete"
    clean = dec["dashboards"]["dash-1"]
    assert clean["action"] == "clean"
    assert clean["expected_version"] == 372
    assert clean["remove_widgets"] == ["w-orphan"]
    assert clean["remove_aliases"] == ["a-dead"]
    assert clean["remove_states"] == []


def test_render_report_contains_key_facts():
    audits = [lib.audit_dashboard(META, FULL), lib.audit_dashboard(META_NP, FULL_NP)]
    md = lib.render_report(audits)
    assert "Mes Installations" in md and "unite_backup" in md
    assert "SUPPRESSION" in md          # marqueur delete
    assert "w-orphan" in md             # orphelin liste
    assert "old_key" in md              # inventaire datakeys


def test_wip_orphan_widget_never_scheduled_for_removal():
    cfg = {
        "widgets": {
            "w-normal-orphan": {"typeFullFqn": "system.cards.html_card", "config": {"title": "Orphan"}},
            "w-wip-orphan": {"typeFullFqn": "tenant.tsmart.foo_wip", "config": {"title": "Draft"}},
        },
        "states": {"menu": {"name": "Menu", "root": True, "layouts": {"main": {"widgets": {}}}}},
        "entityAliases": {},
    }
    full = {"id": {"id": "d9"}, "title": "Mes Installations", "version": 5, "configuration": cfg}
    a = lib.audit_dashboard({"id": {"id": "d9"}, "title": "Mes Installations"}, full)
    # both are orphan facts...
    assert set(a["orphan_widgets"]) == {"w-normal-orphan", "w-wip-orphan"}
    assert [w["id"] for w in a["wip_widgets"]] == ["w-wip-orphan"]
    # ...but the wip one must NOT be scheduled for removal
    dec = lib.build_decisions([a], "2026-07-17T00:00:00")
    assert dec["dashboards"]["d9"]["remove_widgets"] == ["w-normal-orphan"]
    # ...and the report removal checklist must not offer it either
    md = lib.render_report([a])
    assert "w-normal-orphan" in md
    assert "- [ ] `w-wip-orphan`" not in md

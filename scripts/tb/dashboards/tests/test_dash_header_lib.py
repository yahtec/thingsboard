"""Tests unitaires de dash_header_lib : transform pur sur une config synthetique."""
import copy
import json
import os

import dash_header_lib as hdr

# default: photo (col0) + map (col8) sur row0 ; historique: 1 widget ; menu: intouche.
CFG = {
    "widgets": {
        "photo": {"typeFullFqn": "tenant.tsmart.photo_card",
                  "config": {"showTitle": True, "title": "Appareil - Regulateur PAC hybride",
                             "datasources": [{"type": "entity", "entityAliasId": "a-sel"}]}},
        "map":   {"typeFullFqn": "system.map", "config": {"showTitle": False}},
        "hist":  {"typeFullFqn": "tenant.tduo.events_history", "config": {}},
        "menuw": {"typeFullFqn": "tenant.tsmart.menu", "config": {}},
    },
    "states": {
        "default": {"name": "Unite", "layouts": {"main": {"widgets": {
            "photo": {"row": 0, "col": 0, "sizeX": 8, "sizeY": 7},
            "map":   {"row": 0, "col": 8, "sizeX": 16, "sizeY": 7}}}}},
        "historique": {"name": "Hist", "layouts": {"main": {"widgets": {
            "hist": {"row": 0, "col": 0, "sizeX": 24, "sizeY": 14}}}}},
        "menu": {"name": "Menu", "root": True, "layouts": {"main": {"widgets": {
            "menuw": {"row": 0, "col": 0, "sizeX": 24, "sizeY": 9}}}}},
    },
    "entityAliases": {
        "a-sel": {"alias": "Chaufferie selectionnee", "filter": {"type": "stateEntity"}},
    },
}


def _lay(cfg, sid):
    return cfg["states"][sid]["layouts"]["main"]["widgets"]


def test_selected_entity_alias_from_photo():
    assert hdr.selected_entity_alias_id(CFG) == "a-sel"


def test_find_widget_in_state():
    assert hdr.find_widget_in_state(CFG, "default", "tenant.tsmart.photo_card") == "photo"
    assert hdr.find_widget_in_state(CFG, "default", "nope") is None


def test_add_line_inserts_banner_and_shifts():
    out = hdr.add_reminder_line(CFG, "default")
    lay = _lay(out, "default")
    bid = hdr.BANNER_IDS["default"]
    assert bid in lay
    assert lay[bid] == {"row": 0, "col": 0, "sizeX": 24, "sizeY": 1}
    # widgets existants decales de +1
    assert lay["photo"]["row"] == 1 and lay["map"]["row"] == 1
    # definition du widget ajoutee
    assert out["widgets"][bid]["typeFullFqn"] == "system.cards.markdown_card"


def test_add_line_idempotent_no_double_shift():
    once = hdr.add_reminder_line(CFG, "default")
    twice = hdr.add_reminder_line(once, "default")
    assert _lay(twice, "default")["photo"]["row"] == 1  # pas 2
    assert _lay(twice, "default")["map"]["row"] == 1


def test_add_line_absent_state_is_noop():
    out = hdr.add_reminder_line(CFG, "depart_chauffage")  # pas dans CFG
    assert "depart_chauffage" not in out["states"]
    assert hdr.BANNER_IDS["depart_chauffage"] not in (out.get("widgets") or {})


def test_banner_uses_selected_alias():
    out = hdr.add_reminder_line(CFG, "default")
    bid = hdr.BANNER_IDS["default"]
    ds = out["widgets"][bid]["config"]["datasources"][0]
    assert ds["entityAliasId"] == "a-sel" and ds["type"] == "entity"


def test_banner_widget_shape():
    w = hdr.build_banner_widget("x-1", "a-sel")
    assert w["sizeX"] == 24 and w["sizeY"] == 1 and w["row"] == 0 and w["col"] == 0
    c = w["config"]
    assert c["showTitle"] is False
    ds = c["datasources"][0]
    assert ds["entityAliasId"] == "a-sel" and ds["type"] == "entity"
    attr_keys = {k["name"]: k["type"] for k in ds["dataKeys"]}
    assert attr_keys == {"nom_alternatif": "attribute", "nom_residence": "attribute"}
    s = c["settings"]
    assert s["useMarkdownTextFunction"] is True
    assert "nom_residence" in s["markdownTextFunction"]
    assert "nom_alternatif" in s["markdownTextFunction"]
    assert "entityName" in s["markdownTextFunction"]
    assert ".ins-line" in s["markdownCss"] and "space-between" in s["markdownCss"]


def test_strip_photo_title():
    out = hdr.strip_photo_title(CFG)
    assert out["widgets"]["photo"]["config"]["showTitle"] is False


def test_apply_all_covers_present_states_and_strips_title():
    out = hdr.apply_all(CFG)
    # default + historique presents -> banner pose ; menu intouche
    assert hdr.BANNER_IDS["default"] in _lay(out, "default")
    assert hdr.BANNER_IDS["historique"] in _lay(out, "historique")
    assert hdr.BANNER_IDS["default"] not in _lay(out, "menu")
    assert _lay(out, "menu")["menuw"]["row"] == 0  # menu non decale
    assert out["widgets"]["photo"]["config"]["showTitle"] is False


def test_apply_all_idempotent():
    out1 = hdr.apply_all(CFG)
    out2 = hdr.apply_all(out1)
    assert _lay(out2, "default")["photo"]["row"] == 1
    assert _lay(out2, "historique")["hist"]["row"] == 1


def test_add_line_height_change_reflows():
    # 1re pose en hauteur 2 (comme la v374 en prod) : photo 0 -> 2
    h2 = hdr.add_reminder_line(CFG, "default", height=2)
    assert _lay(h2, "default")["photo"]["row"] == 2
    assert _lay(h2, "default")[hdr.BANNER_IDS["default"]]["sizeY"] == 2
    # re-pose en hauteur 1 : la ligne existe deja -> reflow de -1, photo 2 -> 1
    h1 = hdr.add_reminder_line(h2, "default", height=1)
    assert _lay(h1, "default")["photo"]["row"] == 1
    assert _lay(h1, "default")[hdr.BANNER_IDS["default"]]["sizeY"] == 1


def test_no_mutation_of_input():
    before = copy.deepcopy(CFG)
    hdr.add_reminder_line(CFG, "default")
    hdr.strip_photo_title(CFG)
    hdr.apply_all(CFG)
    assert CFG == before


def test_apply_all_on_real_backup_if_present():
    """Garde-fou structurel sur le vrai backup (skip si absent)."""
    here = os.path.dirname(os.path.abspath(__file__))
    bkp = os.path.join(here, "..",
                       "backup-Mes-Installations-0964da30.before_cleanup.20260717-173316.json")
    if not os.path.exists(bkp):
        return  # pas d'echec en CI sans le backup
    dash = json.load(open(bkp, encoding="utf-8"))
    out = hdr.apply_all(hdr.get_config(dash))
    for sid in hdr.HEADER_STATES:
        lay = hdr._state_main_widgets(out, sid)
        if lay is not None:
            assert hdr.BANNER_IDS[sid] in lay, sid
    pid = hdr.find_widget_in_state(out, "default", hdr.PHOTO_FQN)
    assert out["widgets"][pid]["config"]["showTitle"] is False

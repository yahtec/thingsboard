import importlib.util, pathlib, copy
_p = pathlib.Path(__file__).resolve().parents[1] / "menu_toggle_lib.py"
_s = importlib.util.spec_from_file_location("menu_toggle_lib", _p)
mod = importlib.util.module_from_spec(_s); _s.loader.exec_module(mod)

MENU_HTML = ("<div class='menu-top'>...</div>"
             "<div class=\"menu-grid\" id=\"menu-container\"></div>"
             "<script>window.tb_menu_naviguer = function(deviceId){"
             "var b=[{ id:'default', params:{} }];};"
             "var q={entityFilter:{type:'deviceType',deviceTypes:['pac hybride']}};</script>")

def _cfg():
    return {"entityAliases": {"a1": {"alias": "Toutes les chaufferies",
              "filter": {"type": "deviceType", "deviceTypes": ["pac hybride"]}}},
            "widgets": {"w1": {"typeFullFqn": "system.cards.html_value_card",
              "config": {"settings": {"cardHtml": MENU_HTML, "cardCss": ".ch-card{}"}}}},
            "states": {"menu": {"root": True, "layouts": {"main": {"widgets": {"w1": {}}}}}}}

def test_query_broadened():
    out = mod.apply(_cfg())
    html = out["widgets"]["w1"]["config"]["settings"]["cardHtml"]
    assert "deviceTypes:['pac hybride','mchrt']" in html

def test_alias_broadened():
    out = mod.apply(_cfg())
    assert out["entityAliases"]["a1"]["filter"]["deviceTypes"] == ["pac hybride", "mchrt"]

def test_augmentation_script_appended():
    out = mod.apply(_cfg())
    html = out["widgets"]["w1"]["config"]["settings"]["cardHtml"]
    assert "__MCHRT_MENU_V1__" in html
    assert "mchrt_apercu" in html            # nav type-aware
    assert "mchrt-toggle" in html            # ligne bascule

def test_css_appended():
    out = mod.apply(_cfg())
    css = out["widgets"]["w1"]["config"]["settings"]["cardCss"]
    assert ".mchrt-toggle" in css

def test_idempotent():
    a = mod.apply(_cfg()); b = mod.apply(a)
    assert a == b
    assert a["widgets"]["w1"]["config"]["settings"]["cardHtml"].count("__MCHRT_MENU_V1__") == 1

def test_does_not_mutate_input():
    c = _cfg(); before = copy.deepcopy(c); mod.apply(c)
    assert c == before

def test_alias_union_keeps_existing_types():
    c = _cfg()
    c["entityAliases"]["a1"]["filter"]["deviceTypes"] = ["pac hybride", "autre"]
    out = mod.apply(c)
    dts = out["entityAliases"]["a1"]["filter"]["deviceTypes"]
    assert "pac hybride" in dts and "autre" in dts and "mchrt" in dts

def test_missing_query_anchor_raises():
    import pytest
    c = _cfg()
    c["widgets"]["w1"]["config"]["settings"]["cardHtml"] = "<div>no anchor here</div>"
    with pytest.raises(SystemExit):
        mod.apply(c)

def test_aug_script_has_observable_guard():
    out = mod.apply(_cfg())
    html = out["widgets"]["w1"]["config"]["settings"]["cardHtml"]
    assert "console.warn" in html

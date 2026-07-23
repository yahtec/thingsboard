import importlib.util, pathlib, copy
_p = pathlib.Path(__file__).resolve().parents[1] / "mchrt_states_lib.py"
_s = importlib.util.spec_from_file_location("mchrt_states_lib", _p)
mod = importlib.util.module_from_spec(_s); _s.loader.exec_module(mod)

def _cfg():
    grid = {"columns": 48, "minColumns": 48, "rowHeight": 70, "margin": 0,
            "viewFormat": "grid", "autoFillHeight": True, "backgroundColor": "#eeeeee"}
    return {"widgets": {}, "states": {
        "default": {"name": "Unité", "root": True,
                    "layouts": {"main": {"widgets": {}, "gridSettings": grid}}}}}

def test_inserts_two_states():
    out = mod.add_states(_cfg())
    assert out["states"]["mchrt_apercu"]["name"] == "Chaudière"
    assert out["states"]["mchrt_detail"]["name"] == "Détail chaudière"
    assert out["states"]["mchrt_apercu"]["root"] is False

def test_each_state_has_a_widget():
    out = mod.add_states(_cfg())
    for sid, wid in [("mchrt_apercu", mod.APERCU_WID), ("mchrt_detail", mod.DETAIL_WID)]:
        assert wid in out["widgets"]
        assert wid in out["states"][sid]["layouts"]["main"]["widgets"]

def test_grid_copied_from_default():
    out = mod.add_states(_cfg())
    assert out["states"]["mchrt_apercu"]["layouts"]["main"]["gridSettings"]["columns"] == 48

def test_idempotent():
    a = mod.add_states(_cfg()); b = mod.add_states(a)
    assert a == b

def test_does_not_mutate_input():
    c = _cfg(); before = copy.deepcopy(c); mod.add_states(c)
    assert c == before

def test_stored_widget_has_id_and_layout_fields():
    out = mod.add_states(_cfg())
    for wid in (mod.APERCU_WID, mod.DETAIL_WID):
        w = out["widgets"][wid]
        assert w["id"] == wid
        for f in ("row", "col", "sizeX", "sizeY"):
            assert f in w, f

def test_widget_ids_are_valid_uuid():
    import uuid
    for wid in (mod.APERCU_WID, mod.DETAIL_WID):
        uuid.UUID(wid)  # ValueError if not a well-formed UUID

import importlib.util, pathlib
_p = pathlib.Path(__file__).resolve().parents[1] / "build_mchrt_profile.py"
_s = importlib.util.spec_from_file_location("build_mchrt_profile", _p)
mod = importlib.util.module_from_spec(_s); _s.loader.exec_module(mod)

def test_name_is_lowercase_mchrt():
    body = mod.build("11111111-2222-3333-4444-555555555555")
    assert body["name"] == "mchrt"            # == device.type

def test_points_at_given_chain():
    body = mod.build("11111111-2222-3333-4444-555555555555")
    assert body["defaultRuleChainId"] == {
        "entityType": "RULE_CHAIN", "id": "11111111-2222-3333-4444-555555555555"}

def test_no_alarms_yet():
    body = mod.build("11111111-2222-3333-4444-555555555555")
    assert body["profileData"]["alarms"] in (None, [])

def test_transport_and_provision_defaults():
    body = mod.build("x")
    assert body["type"] == "DEFAULT"
    assert body["transportType"] == "DEFAULT"
    assert body["provisionType"] == "DISABLED"

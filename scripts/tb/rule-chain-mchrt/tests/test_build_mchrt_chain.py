import importlib.util, pathlib
_p = pathlib.Path(__file__).resolve().parents[1] / "build_mchrt_chain.py"
_s = importlib.util.spec_from_file_location("build_mchrt_chain", _p)
mod = importlib.util.module_from_spec(_s); _s.loader.exec_module(mod)

def test_metadata_has_only_save_and_profile():
    meta = mod.build_metadata()
    names = [n["name"] for n in meta["nodes"]]
    assert names == ["Save Timeseries", "DeviceProfile (alarms)"]
    assert meta["firstNodeIndex"] == 0

def test_no_reassign_nodes():
    meta = mod.build_metadata()
    blob = str(meta).lower()
    for forbidden in ["assign", "yahtec", "tbel", "filter hps", "evt "]:
        assert forbidden not in blob, forbidden

def test_save_wired_to_profile():
    meta = mod.build_metadata()
    assert {"fromIndex": 0, "toIndex": 1, "type": "Success"} in meta["connections"]

def test_node_types():
    meta = mod.build_metadata()
    assert meta["nodes"][0]["type"].endswith("TbMsgTimeseriesNode")
    assert meta["nodes"][1]["type"].endswith("TbDeviceProfileNode")

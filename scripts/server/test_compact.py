#!/usr/bin/env python3
"""
scripts/server/test_compact.py

Tests unitaires offline du mapping inverse v1 -> v2 dans compact-v1-to-v2.py.

Usage : python3 test_compact.py
"""

import sys

# Import depuis le module sibling (les deux fichiers sont co-locaux)
sys.path.insert(0, '.')
try:
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("compact", "compact-v1-to-v2.py")
    compact = module_from_spec(spec)
    spec.loader.exec_module(compact)
    build_pac_v2 = compact.build_pac_v2
except Exception as e:
    sys.exit(f"Failed to import compact-v1-to-v2.py : {e}")


def test_top_level():
    flat = {
        "id": "2602000001",
        "rel": 1.4,
        "type": 0,
        "nHp": 1,
        "tExt": 33.4,
        "TinM": 6.9,
        "press": 2,
        "commCm2": 0,
        "relCm2": 0,
        "date": "29/05/26",
        "time": "13:05:37",
        "dateTime": "29/05/26 11:05:38",
    }
    r = build_pac_v2(flat)
    assert r["id"] == "2602000001", f"id wrong : {r['id']}"
    assert r["rel"] == 1.4, f"rel wrong : {r['rel']}"
    assert r["type"] == 0, f"type wrong : {r['type']}"
    assert r["nHp"] == 1, f"nHp wrong : {r['nHp']}"
    assert r["tExt"] == 33.4
    assert r["TinM"] == 6.9
    assert r["press"] == 2
    assert r["commCm2"] == 0
    assert r["relCm2"] == 0
    assert r["date"] == "29/05/26"
    assert r["time"] == "13:05:37"
    assert r["dateTime"] == "29/05/26 11:05:38"
    print("OK test_top_level")


def test_HP_subkeys():
    flat = {
        "HP1_status": 4,
        "HP1_pHi": 14.7,
        "HP1_pLo": 4.1,
        "HP1_dpf": 734,
        "HP1_invert_comm": False,
        "HP1_invert_freq": 59,
        "HP1_invert_pwr": 3338,
        "HP1_boil_status": 0,
        "HP1_boil_tOut": 6.9,
        "HP1_boil_press": 2,
        "HP1_pump_comm": False,
        "HP1_pump_pwr": 1870,
        "HP1_pump_dP": 10.1,
        "HP1_comm": True,
        "HP1_relStm": "1.3.137",
        "HP1_relEsp": "1.0.145",
        "HP1_relScr": "1.0.202",
    }
    r = build_pac_v2(flat)
    hp = r["HPs"][0]
    # HP sub-keys
    assert hp["HP"]["status"] == 4, f"HP1.HP.status wrong : {hp['HP']['status']}"
    assert hp["HP"]["pHi"] == 14.7
    assert hp["HP"]["pLo"] == 4.1
    assert hp["HP"]["dpf"] == 734
    # invert
    assert hp["invert"]["comm"] is False
    assert hp["invert"]["freq"] == 59
    assert hp["invert"]["pwr"] == 3338
    # boil
    assert hp["boil"]["status"] == 0
    assert hp["boil"]["tOut"] == 6.9
    assert hp["boil"]["press"] == 2
    # pump
    assert hp["pump"]["comm"] is False
    assert hp["pump"]["pwr"] == 1870
    assert hp["pump"]["dP"] == 10.1
    # direct (not under HP)
    assert hp["comm"] is True, f"HP1.comm should be top-level under HPs[0], got HPs[0].comm={hp.get('comm')}"
    assert hp["relStm"] == "1.3.137"
    assert hp["relEsp"] == "1.0.145"
    assert hp["relScr"] == "1.0.202"
    print("OK test_HP_subkeys")


def test_HPs_array_length():
    flat = {"HP1_status": 4}
    r = build_pac_v2(flat)
    assert len(r["HPs"]) == 4, f"HPs len should be 4 (fixed), got {len(r['HPs'])}"
    # Slot inactif HP2/HP3/HP4 doivent avoir les sous-structures init mais vides
    for i in (1, 2, 3):
        assert "HP" in r["HPs"][i]
        assert r["HPs"][i]["HP"] == {}
        assert r["HPs"][i]["invert"] == {}
        assert r["HPs"][i]["boil"] == {}
        assert r["HPs"][i]["pump"] == {}
    print("OK test_HPs_array_length")


def test_heat():
    flat = {
        "heat_tOut": 0,
        "heat_tIn": 0,
        "heat_posV3V": 100,
        "heat_slope": 1.8,
        "heat_foot": 20,
        "heat_setpoint": 45,
        "heat_tCut": 20,
        "heat_calo_qe": 11578,
        "heat_calo_qeU": 2875,
        "heat_calo_tIn": 55.85,
    }
    r = build_pac_v2(flat)
    assert r["heat"]["tOut"] == 0
    assert r["heat"]["posV3V"] == 100
    assert r["heat"]["slope"] == 1.8
    assert r["heat"]["setpoint"] == 45
    assert r["heat"]["calo"]["qe"] == 11578
    assert r["heat"]["calo"]["qeU"] == 2875
    assert r["heat"]["calo"]["tIn"] == 55.85
    print("OK test_heat")


def test_dhw_4_pumps():
    flat = {
        "dhw_tOut": 60.2,
        "dhw_tIn": 45.2,
        "dhw_tTank": 59.2,
        "dhw_tSet": 60,
        "dhw_posV3V": 100,
        "dhw_pump1_pwr": 200,
        "dhw_pump1_dP": 7.5,
        "dhw_pump2_qe": 0,
        "dhw_pump3_rpm": 4555,
        "dhw_pump4_time": 4000,
    }
    r = build_pac_v2(flat)
    assert r["dhw"]["tOut"] == 60.2
    assert r["dhw"]["posV3V"] == 100
    assert r["dhw"]["tSet"] == 60
    assert r["dhw"]["pump1"]["pwr"] == 200
    assert r["dhw"]["pump1"]["dP"] == 7.5
    assert r["dhw"]["pump2"]["qe"] == 0
    assert r["dhw"]["pump3"]["rpm"] == 4555
    assert r["dhw"]["pump4"]["time"] == 4000
    print("OK test_dhw_4_pumps")


def test_caloM():
    flat = {
        "caloM_tIn": 0,
        "caloM_tRet": 0,
        "caloM_qe": 0,
        "caloM_qeU": 2875,
        "caloM_pwr": 250,
        "caloM_pwrU": 2860,
    }
    r = build_pac_v2(flat)
    assert r["caloM"]["tIn"] == 0
    assert r["caloM"]["qeU"] == 2875
    assert r["caloM"]["pwr"] == 250
    assert r["caloM"]["pwrU"] == 2860
    print("OK test_caloM")


def test_pump_module():
    flat = {
        "pump1M_pwr": 200,
        "pump1M_dP": 7.5,
        "pump1M_qe": 3.0,
        "pump2M_pwr": 0,
        "pump2M_time": 4000,
    }
    r = build_pac_v2(flat)
    assert r["pump1M"]["pwr"] == 200
    assert r["pump1M"]["dP"] == 7.5
    assert r["pump1M"]["qe"] == 3.0
    assert r["pump2M"]["pwr"] == 0
    assert r["pump2M"]["time"] == 4000
    print("OK test_pump_module")


def test_partial_payload():
    """Si un sample n'a que quelques keys (firmware partiel), pas d'erreur."""
    flat = {
        "id": "2602000001",
        "type": 0,
    }
    r = build_pac_v2(flat)
    assert r["id"] == "2602000001"
    assert r["type"] == 0
    # Sous-structures vides mais presentes (init)
    assert len(r["HPs"]) == 4
    assert r["heat"] == {"calo": {}}
    assert r["dhw"] == {"pump1": {}, "pump2": {}, "pump3": {}, "pump4": {}}
    print("OK test_partial_payload")


def test_full_payload_realistic():
    """Test avec un payload realiste capturee en prod (2602000001)."""
    flat = {
        # top-level
        "id": "2602000001", "rel": 1.4, "type": 0, "nHp": 1,
        "tExt": 33.4, "TinM": 6.9, "press": 2,
        "commCm2": 0, "relCm2": 0,
        "date": "29/05/26", "time": "13:05:37", "dateTime": "29/05/26 11:05:38",
        # HP1 actif
        "HP1_status": 4, "HP1_pHi": 14.7, "HP1_pLo": 4.1,
        "HP1_pAir": 13, "HP1_tIn": 10.8, "HP1_tOut": 7,
        "HP1_invert_freq": 59, "HP1_invert_volt": 208, "HP1_invert_pwr": 3338,
        "HP1_boil_status": 0, "HP1_boil_tOut": 6.9, "HP1_boil_qe": 2056,
        "HP1_pump_pwr": 1870, "HP1_pump_dP": 10.1,
        "HP1_comm": True, "HP1_relStm": "1.3.137",
        # heat
        "heat_tOut": 0, "heat_tIn": 0, "heat_posV3V": 100,
        "heat_slope": 0, "heat_setpoint": 7,
        "heat_calo_qe": 0, "heat_calo_qeU": 0,
        # dhw
        "dhw_tOut": 0, "dhw_tIn": 0, "dhw_tSet": 0, "dhw_posV3V": 100,
        "dhw_pump1_pwr": 0, "dhw_pump2_pwr": 0, "dhw_pump3_pwr": 0, "dhw_pump4_pwr": 0,
        # caloM
        "caloM_tIn": 0, "caloM_qe": 0,
        # pump module
        "pump1M_pwr": 0, "pump2M_pwr": 0,
    }
    r = build_pac_v2(flat)
    # Sanity checks
    assert r["id"] == "2602000001"
    assert len(r["HPs"]) == 4
    assert r["HPs"][0]["HP"]["status"] == 4
    assert r["HPs"][0]["HP"]["pAir"] == 13
    assert r["HPs"][0]["invert"]["freq"] == 59
    assert r["HPs"][0]["boil"]["qe"] == 2056
    assert r["HPs"][0]["pump"]["dP"] == 10.1
    assert r["HPs"][0]["comm"] is True
    assert r["HPs"][0]["relStm"] == "1.3.137"
    assert r["heat"]["setpoint"] == 7
    assert r["heat"]["posV3V"] == 100
    assert r["heat"]["calo"]["qeU"] == 0
    assert r["dhw"]["posV3V"] == 100
    assert all(r["dhw"][f"pump{i}"]["pwr"] == 0 for i in (1, 2, 3, 4))
    assert r["caloM"]["qe"] == 0
    print("OK test_full_payload_realistic")


def main():
    test_top_level()
    test_HP_subkeys()
    test_HPs_array_length()
    test_heat()
    test_dhw_4_pumps()
    test_caloM()
    test_pump_module()
    test_partial_payload()
    test_full_payload_realistic()
    print("\n[ALL TESTS PASSED]")


if __name__ == "__main__":
    main()

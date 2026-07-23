"""Métadonnées d'une rule chain MCHRT minimale : Save Timeseries -> DeviceProfile.
Aucun nœud d'assignation client (contrairement à 'PAC Hybride Router') => pas de
clobber possible, pas de garde site_assigned nécessaire. Transform pur, sans I/O."""

CHAIN_NAME = "MCHRT Router"

def _save_ts_node():
    return {
        "type": "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode",
        "name": "Save Timeseries",
        "debugMode": False, "singletonMode": False,
        "configuration": {"defaultTTL": 0, "useServerTs": False,
                          "processingSettings": {"type": "ON_EVERY_MESSAGE"}},
        "additionalInfo": {"layoutX": 420, "layoutY": 180},
    }

def _device_profile_node():
    return {
        "type": "org.thingsboard.rule.engine.profile.TbDeviceProfileNode",
        "name": "DeviceProfile (alarms)",
        "debugMode": False, "singletonMode": False,
        "configuration": {"persistAlarmRulesState": False,
                          "fetchAlarmRulesStateOnStart": False},
        "additionalInfo": {"layoutX": 720, "layoutY": 180},
    }

def build_metadata():
    return {
        "firstNodeIndex": 0,
        "nodes": [_save_ts_node(), _device_profile_node()],
        "connections": [{"fromIndex": 0, "toIndex": 1, "type": "Success"}],
        "ruleChainConnections": None,
    }

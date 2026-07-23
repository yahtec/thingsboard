"""Corps JSON du device profile 'mchrt' (POST /api/deviceProfile). Transform pur.
⚠ En TB, device.type == nom du profil : le nom DOIT être 'mchrt'."""

PROFILE_NAME = "mchrt"

def build(default_rule_chain_id):
    return {
        "name": PROFILE_NAME,
        "description": "Chaudière MCHRT (télémétrie chaudière) — ossature, payload différé",
        "type": "DEFAULT",
        "transportType": "DEFAULT",
        "provisionType": "DISABLED",
        "defaultRuleChainId": {"entityType": "RULE_CHAIN", "id": default_rule_chain_id},
        "defaultQueueName": "Main",
        "profileData": {
            "configuration": {"type": "DEFAULT"},
            "transportConfiguration": {"type": "DEFAULT"},
            "provisionConfiguration": {"type": "DISABLED", "provisionDeviceSecret": None},
            "alarms": None,
        },
    }

"""Insère les états stub 'mchrt_apercu' / 'mchrt_detail' dans la config dashboard.
Transform pur, deep-copie, idempotent. Le contenu réel (map/photo/détail) est différé :
un seul widget markdown placeholder par état, pour rendre l'état navigable."""
import copy

STATE_APERCU = "mchrt_apercu"
STATE_DETAIL = "mchrt_detail"
APERCU_WID = "0bc70001-0000-0000-0000-000000000001"
DETAIL_WID = "0bc70002-0000-0000-0000-000000000002"

def _placeholder_widget(wid, title, body_md):
    return {
        "id": wid,
        "typeFullFqn": "system.cards.markdown_card",
        "type": "latest",
        "config": {"showTitle": False, "dropShadow": True, "enableFullscreen": False,
                   "datasources": [], "timewindow": {"realtime": {"timewindowMs": 60000}},
                   "settings": {"markdownTextPattern": body_md, "useMarkdownTextFunction": False},
                   "title": title},
        "row": 0, "col": 0, "sizeX": 24, "sizeY": 6,
    }

def _grid(cfg):
    return copy.deepcopy(cfg["states"]["default"]["layouts"]["main"].get("gridSettings", {}))

def add_states(cfg):
    cfg = copy.deepcopy(cfg)
    if STATE_APERCU in cfg["states"]:
        return cfg  # idempotent
    plan = [
        (STATE_APERCU, "Chaudière", APERCU_WID,
         "## Chaudière\n\n_Vue d'ensemble (carte + photo) — à compléter._"),
        (STATE_DETAIL, "Détail chaudière", DETAIL_WID,
         "## Détail chaudière\n\n_Détail chaudière — à compléter (données non figées)._"),
    ]
    for sid, name, wid, md in plan:
        w = _placeholder_widget(wid, name, md)
        pos = {"row": w["row"], "col": w["col"], "sizeX": w["sizeX"], "sizeY": w["sizeY"]}
        cfg["widgets"][wid] = w
        cfg["states"][sid] = {"name": name, "root": False,
            "layouts": {"main": {"widgets": {wid: pos}, "gridSettings": _grid(cfg)}}}
    return cfg

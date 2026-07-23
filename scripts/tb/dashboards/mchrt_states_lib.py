"""Insère les états stub 'mchrt_apercu' / 'mchrt_detail' dans la config dashboard.
Transform pur, deep-copie, idempotent. Le contenu réel (map/photo/détail) est différé :
un seul widget markdown placeholder par état, pour rendre l'état navigable."""
import copy

STATE_APERCU = "mchrt_apercu"
STATE_DETAIL = "mchrt_detail"
APERCU_WID = "0mch0001-0000-0000-0000-000000000001"
DETAIL_WID = "0mch0002-0000-0000-0000-000000000002"

def _placeholder_widget(title, body_md):
    return {
        "typeFullFqn": "system.cards.markdown_card",
        "type": "latest", "showTitle": False,
        "config": {"showTitle": False, "dropShadow": True, "enableFullscreen": False,
                   "datasources": [], "timewindow": {"realtime": {"timewindowMs": 60000}},
                   "settings": {"markdownTextPattern": body_md, "useMarkdownTextFunction": False},
                   "title": title},
        "row": 0, "col": 0, "sizeX": 24, "sizeY": 6,
    }

def _grid(cfg):
    return copy.deepcopy(cfg["states"]["default"]["layouts"]["main"]["gridSettings"])

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
        w = _placeholder_widget(name, md)
        pos = {"row": w.pop("row"), "col": w.pop("col"),
               "sizeX": w.pop("sizeX"), "sizeY": w.pop("sizeY")}
        cfg["widgets"][wid] = w
        cfg["states"][sid] = {"name": name, "root": False,
            "layouts": {"main": {"widgets": {wid: pos}, "gridSettings": _grid(cfg)}}}
    return cfg

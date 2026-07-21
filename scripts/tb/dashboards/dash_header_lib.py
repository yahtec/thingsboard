"""Logique pure (aucune I/O) : pose une ligne de rappel installation en haut des
etats de detail de 'Mes Installations' et retire le titre de la carte photo.
cfg = le champ configuration d'un dashboard TB. Ne mute jamais l'entree."""
import copy

HEADER_STATES = ['default', 'depart_chauffage', 'ecs', 'donnees_HP1',
                 'fault_diagnostic', 'historique']
HEADER_H = 2
# ids deterministes = marqueur d'idempotence (segment '0b17' libre dans ce dashboard).
BANNER_IDS = {
    'default':          'a1b2c3d4-0b17-4000-a000-000000000001',
    'depart_chauffage': 'a1b2c3d4-0b17-4000-a000-000000000002',
    'ecs':              'a1b2c3d4-0b17-4000-a000-000000000003',
    'donnees_HP1':      'a1b2c3d4-0b17-4000-a000-000000000004',
    'fault_diagnostic': 'a1b2c3d4-0b17-4000-a000-000000000005',
    'historique':       'a1b2c3d4-0b17-4000-a000-000000000006',
}
PHOTO_FQN = 'tenant.tsmart.photo_card'
_MARKDOWN_TYPE_ID = {'id': '5ff7fcd0-3d7d-11f1-8ec8-ef2af873172d',
                     'entityType': 'WIDGET_TYPE'}

# Rendu : label a gauche (masque si vide OU == serial), n serie a droite.
_BANNER_FN = (
    "var ds = (data && data[0] && data[0].datasource) || "
    "(ctx && ctx.datasources && ctx.datasources[0]) || {};\n"
    "var serial = ds.entityName || '';\n"
    "var label = ds.entityLabel || '';\n"
    "var name = (label && label !== serial) ? label : '';\n"
    "var left = '<span class=\"ins-name\">' + name + '</span>';\n"
    "var right = serial ? '<span class=\"ins-serial\">N&deg; de s&eacute;rie ' "
    "+ serial + '</span>' : '';\n"
    "return '<div class=\"ins-line\">' + left + right + '</div>';"
)
_BANNER_CSS = (
    ".tb-markdown-view{height:100%!important;min-height:100%!important;"
    "padding:0!important;background:transparent;overflow:hidden!important;}\n"
    ".ins-line{display:flex;align-items:center;justify-content:space-between;"
    "height:100%;box-sizing:border-box;padding:0 16px;background:#f5f6f8;"
    "border-bottom:1px solid #e0e0e0;font-family:-apple-system,BlinkMacSystemFont,"
    "'Segoe UI',Roboto,Arial,sans-serif;}\n"
    ".ins-name{font-weight:700;font-size:15px;color:#1f2933;white-space:nowrap;"
    "overflow:hidden;text-overflow:ellipsis;}\n"
    ".ins-serial{font-size:13px;color:#6b7280;white-space:nowrap;margin-left:12px;}"
)


def get_config(dash):
    if isinstance(dash, dict) and 'configuration' in dash:
        return dash['configuration'] or {}
    return dash or {}


def _state_main_widgets(cfg, sid):
    """dict des widgets du layout 'main' de l'etat sid, ou None si absent."""
    st = (cfg.get('states') or {}).get(sid)
    if not st:
        return None
    return (st.get('layouts') or {}).get('main', {}).get('widgets')


def find_widget_in_state(cfg, sid, fqn):
    """Premier id de widget de l'etat sid dont typeFullFqn == fqn, sinon None."""
    lay = _state_main_widgets(cfg, sid) or {}
    wdefs = cfg.get('widgets') or {}
    for wid in lay:
        if (wdefs.get(wid) or {}).get('typeFullFqn') == fqn:
            return wid
    return None


def selected_entity_alias_id(cfg):
    """Alias 'installation selectionnee' : celui de la carte photo (default),
    sinon le premier alias stateEntity, sinon None."""
    pid = find_widget_in_state(cfg, 'default', PHOTO_FQN)
    if pid:
        ds = (((cfg.get('widgets') or {}).get(pid) or {}).get('config') or {}
              ).get('datasources') or []
        if ds and ds[0].get('entityAliasId'):
            return ds[0]['entityAliasId']
    for aid, a in (cfg.get('entityAliases') or {}).items():
        if (a.get('filter') or {}).get('type') == 'stateEntity':
            return aid
    return None


def build_banner_widget(wid, alias_id):
    """Definition complete du widget markdown_card 'ligne de rappel'."""
    return {
        'id': wid,
        'typeFullFqn': 'system.cards.markdown_card',
        'typeId': dict(_MARKDOWN_TYPE_ID),
        'type': 'latest',
        'sizeX': 24, 'sizeY': HEADER_H, 'row': 0, 'col': 0,
        'config': {
            'showTitle': False,
            'title': 'Rappel installation',
            'dropShadow': False,
            'enableFullscreen': False,
            'padding': '0px',
            'margin': '0px',
            'backgroundColor': 'rgba(0, 0, 0, 0)',
            'color': 'rgba(0, 0, 0, 0.87)',
            'datasources': [{'type': 'entity', 'name': '',
                             'dataKeys': [], 'entityAliasId': alias_id}],
            'settings': {
                'useMarkdownTextFunction': True,
                'markdownTextFunction': _BANNER_FN,
                'markdownTextPattern': '',
                'markdownCss': _BANNER_CSS,
                'applyDefaultMarkdownStyle': False,
            },
        },
    }


def add_reminder_line(cfg, sid, height=HEADER_H):
    """COPIE de cfg avec la ligne de rappel en row=0 de l'etat sid.
    Idempotent : si deja presente, met a jour def/position SANS re-decaler."""
    out = copy.deepcopy(cfg)
    lay = _state_main_widgets(out, sid)
    if lay is None:
        return out
    wid = BANNER_IDS[sid]
    alias_id = selected_entity_alias_id(out)
    if wid not in lay:
        for l in lay.values():
            l['row'] = l.get('row', 0) + height
    out.setdefault('widgets', {})[wid] = build_banner_widget(wid, alias_id)
    lay[wid] = {'row': 0, 'col': 0, 'sizeX': 24, 'sizeY': height}
    return out


def strip_photo_title(cfg):
    """COPIE de cfg avec showTitle=False sur la carte photo de l'etat default."""
    out = copy.deepcopy(cfg)
    pid = find_widget_in_state(out, 'default', PHOTO_FQN)
    if pid:
        (out['widgets'][pid].setdefault('config', {}))['showTitle'] = False
    return out


def apply_all(cfg):
    """Ligne de rappel sur les 6 etats de detail + retrait titre photo."""
    out = cfg
    for sid in HEADER_STATES:
        out = add_reminder_line(out, sid)
    return strip_photo_title(out)

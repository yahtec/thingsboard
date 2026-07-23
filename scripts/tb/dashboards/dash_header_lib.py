"""Logique pure (aucune I/O) : pose une ligne de rappel installation en haut des
etats de detail de 'Mes Installations' et retire le titre de la carte photo.
cfg = le champ configuration d'un dashboard TB. Ne mute jamais l'entree."""
import copy

HEADER_H = 1
# ids deterministes = marqueur d'idempotence (segment '0b17' libre dans ce dashboard).
BANNER_IDS = {
    'default':          'a1b2c3d4-0b17-4000-a000-000000000001',
    'depart_chauffage': 'a1b2c3d4-0b17-4000-a000-000000000002',
    'ecs':              'a1b2c3d4-0b17-4000-a000-000000000003',
    'donnees_HP1':      'a1b2c3d4-0b17-4000-a000-000000000004',
    'fault_diagnostic': 'a1b2c3d4-0b17-4000-a000-000000000005',
    'historique':       'a1b2c3d4-0b17-4000-a000-000000000006',
    "mchrt_apercu": "0b170007-0000-0000-0000-000000000007",
    "mchrt_detail": "0b170008-0000-0000-0000-000000000008",
}
# derive des cles de BANNER_IDS (ordre d'insertion) -> pas de liste a maintenir en lockstep.
HEADER_STATES = list(BANNER_IDS)
PHOTO_FQN = 'tenant.tsmart.photo_card'
# UUID du widget-type markdown_card, specifique a cette instance TB ; TB resout surtout
# via typeFullFqn, cet id est une securite. A revalider si on change d'instance.
_MARKDOWN_TYPE_ID = {'id': '5ff7fcd0-3d7d-11f1-8ec8-ef2af873172d',
                     'entityType': 'WIDGET_TYPE'}

_BANNER_FN = (
    "var ctxRef = (typeof ctx !== 'undefined' && ctx) ? ctx : "
    "((typeof self !== 'undefined' && self.ctx) ? self.ctx : null);\n"
    "function attr(re){ var v=''; var arr=(ctxRef && ctxRef.data) || []; "
    "for(var i=0;i<arr.length;i++){ var d=arr[i]; "
    "if(d && d.dataKey && re.test(d.dataKey.name) && d.data && d.data.length){ "
    "v = d.data[d.data.length-1][1]; } } return (v==null?'':String(v)).trim(); }\n"
    "var d0 = ctxRef && ctxRef.datasources && ctxRef.datasources[0];\n"
    "var serial = (d0 && (d0.entityName || (d0.entity && d0.entity.name))) || '';\n"
    "var name = attr(/^nom_alternatif$/i) || attr(/^nom_residence$/i);\n"
    "var left = '<span class=\"ins-name\">' + name + '</span>';\n"
    "var right = serial ? '<span class=\"ins-serial\">N&deg; de s&eacute;rie ' "
    "+ serial + '</span>' : '';\n"
    "return '<div class=\"ins-line\">' + left + right + '</div>';"
)
_BANNER_CSS = (
    ".tb-markdown-view{height:100%!important;min-height:100%!important;"
    "padding:0!important;background:transparent;overflow:hidden!important;}\n"
    ".ins-line{display:flex;align-items:center;justify-content:space-between;"
    "height:44px;max-height:100%;box-sizing:border-box;padding:0 18px;"
    "background:#f5f6f8;border-bottom:1px solid #e0e0e0;"
    "font-family:-apple-system,BlinkMacSystemFont,"
    "'Segoe UI',Roboto,Arial,sans-serif;line-height:1.2;}\n"
    ".ins-name{font-weight:700;font-size:18px;color:#1f2933;white-space:nowrap;"
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
    """Definition complete du widget markdown_card 'ligne de rappel'.
    Lit nom_alternatif/nom_residence (attributs) + entityName via la fonction."""
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
            'datasources': [{
                'type': 'entity', 'name': '',
                'entityAliasId': alias_id,
                'dataKeys': [
                    {'name': 'nom_alternatif', 'type': 'attribute',
                     'label': 'nom_alternatif', 'color': '#2196f3', 'settings': {}},
                    {'name': 'nom_residence', 'type': 'attribute',
                     'label': 'nom_residence', 'color': '#4caf50', 'settings': {}},
                ],
            }],
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
    Idempotent ET correct en hauteur : si la ligne est deja presente, decale les
    autres widgets de (height - ancienne_hauteur) — 0 si inchangee — au lieu de
    re-decaler de height ; premiere pose = decalage de +height."""
    out = copy.deepcopy(cfg)
    lay = _state_main_widgets(out, sid)
    if lay is None:
        return out
    wid = BANNER_IDS[sid]
    alias_id = selected_entity_alias_id(out)
    if wid in lay:
        delta = height - lay[wid].get('sizeY', height)
        if delta:
            for k, l in lay.items():
                if k != wid:
                    l['row'] = l.get('row', 0) + delta
    else:
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

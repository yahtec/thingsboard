"""Logique pure (aucune I/O) d'analyse et de transformation de configs dashboard TB.
Testable sans reseau. `cfg` = le champ `configuration` d'un dashboard TB."""
import copy
import re

_WIP_RE = re.compile(r'wip', re.IGNORECASE)
_NONPROD_RE = re.compile(r'(test|backup|wip)', re.IGNORECASE)
_ALIAS_KEYS = ('entityAliasId', 'targetDeviceAliasId', 'aliasId')


def get_config(dash):
    """Retourne la config, qu'on passe le dashboard complet ou deja la config."""
    if isinstance(dash, dict) and 'configuration' in dash:
        return dash['configuration'] or {}
    return dash or {}


def placed_widget_ids(cfg):
    """Ids de widgets references dans au moins un layout de state."""
    ids = set()
    for s in (cfg.get('states') or {}).values():
        for lay in (s.get('layouts') or {}).values():
            ids |= set((lay.get('widgets') or {}).keys())
    return ids


def find_orphan_widgets(cfg):
    """Ids dans configuration.widgets absents de tout layout -> jamais rendus. Trie."""
    return sorted(set((cfg.get('widgets') or {}).keys()) - placed_widget_ids(cfg))


def collect_used_alias_ids(cfg):
    """Tous les alias ids references n'importe ou (recursif)."""
    used = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _ALIAS_KEYS and isinstance(v, str):
                    used.add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cfg)
    return used


def find_dead_aliases(cfg):
    """Ids d'entityAliases jamais references. Trie."""
    return sorted(set((cfg.get('entityAliases') or {}).keys()) - collect_used_alias_ids(cfg))


def find_wip_widgets(cfg):
    """[{id,title,fqn}] pour widgets dont fqn OU titre contient 'wip'. Trie par id."""
    out = []
    for wid, w in (cfg.get('widgets') or {}).items():
        fqn = w.get('typeFullFqn') or ''
        title = (w.get('config') or {}).get('title') or ''
        if _WIP_RE.search(fqn) or _WIP_RE.search(title):
            out.append({'id': wid, 'title': title, 'fqn': fqn})
    return sorted(out, key=lambda x: x['id'])


def list_states(cfg):
    """[{id,name,root,widget_count}] pour tous les states. Trie par id."""
    out = []
    for sid, s in (cfg.get('states') or {}).items():
        n = sum(len(lay.get('widgets') or {}) for lay in (s.get('layouts') or {}).values())
        out.append({'id': sid, 'name': s.get('name', '?'),
                    'root': bool(s.get('root')), 'widget_count': n})
    return sorted(out, key=lambda x: x['id'])


def list_datakeys(cfg):
    """[{widget_id,widget_title,key_name,key_type}] pour tous les dataKeys des datasources.
    Inventaire pour revue manuelle (pas de preuve de liveness -- cf. spec). Trie."""
    out = []
    for wid, w in (cfg.get('widgets') or {}).items():
        title = (w.get('config') or {}).get('title') or ''
        for ds in ((w.get('config') or {}).get('datasources') or []):
            for dk in (ds.get('dataKeys') or []):
                out.append({'widget_id': wid, 'widget_title': title,
                            'key_name': dk.get('name', '?'), 'key_type': dk.get('type', '?')})
    return sorted(out, key=lambda x: (x['widget_id'], x['key_name']))


def classify(title):
    """'nonprod' si titre matche test/backup/wip, sinon 'prod'. Advisory."""
    return 'nonprod' if _NONPROD_RE.search(title or '') else 'prod'


def remove_items(cfg, remove_widgets=(), remove_aliases=(), remove_states=()):
    """Retourne une COPIE de cfg avec les ids retires :
      - remove_widgets : retires de widgets ET de chaque layout de state
      - remove_aliases : retires de entityAliases
      - remove_states  : retires de states (avec leur layout)
    Ne mute pas l'original. Ids inconnus ignores (idempotent)."""
    out = copy.deepcopy(cfg)
    rw, ra, rs = set(remove_widgets), set(remove_aliases), set(remove_states)

    for wid in rw:
        (out.get('widgets') or {}).pop(wid, None)
    for aid in ra:
        (out.get('entityAliases') or {}).pop(aid, None)
    for sid in rs:
        (out.get('states') or {}).pop(sid, None)

    for s in (out.get('states') or {}).values():
        for lay in (s.get('layouts') or {}).values():
            lw = lay.get('widgets') or {}
            for wid in rw:
                lw.pop(wid, None)
    return out

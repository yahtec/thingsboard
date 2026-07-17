"""Logique pure (aucune I/O) d'analyse et de transformation de configs dashboard TB.
Testable sans reseau. `cfg` = le champ `configuration` d'un dashboard TB."""
import copy
import json
import re

_WIP_RE = re.compile(r'wip', re.IGNORECASE)
_NONPROD_RE = re.compile(r'(test|backup|wip)', re.IGNORECASE)


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


def find_dead_aliases(cfg):
    """Ids d'entityAliases dont l'UUID n'apparait NULLE PART ailleurs dans la config.
    Scan brut de l'UUID (36 car.) -> robuste a toute cle de reference : entityAliasId,
    targetDeviceAliasId(s), dsEntityAliasId, ou toute cle future. Trie."""
    aliases = cfg.get('entityAliases') or {}
    if not aliases:
        return []
    rest_blob = json.dumps({k: v for k, v in cfg.items() if k != 'entityAliases'},
                           ensure_ascii=False)
    dead = []
    for aid in aliases:
        others_blob = json.dumps({k: v for k, v in aliases.items() if k != aid},
                                 ensure_ascii=False)
        if aid not in rest_blob and aid not in others_blob:
            dead.append(aid)
    return sorted(dead)


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


def audit_dashboard(meta, full):
    """Verdict complet d'un dashboard (meta = entree /api/tenant/dashboards, full = /api/dashboard/{id})."""
    cfg = get_config(full)
    title = meta.get('title') or full.get('title') or '?'
    did = (meta.get('id') or {}).get('id') or (full.get('id') or {}).get('id')
    return {
        'id': did,
        'title': title,
        'version': full.get('version'),
        'classification': classify(title),
        'counts': {'widgets': len(cfg.get('widgets') or {}),
                   'states': len(cfg.get('states') or {}),
                   'aliases': len(cfg.get('entityAliases') or {})},
        'orphan_widgets': find_orphan_widgets(cfg),
        'dead_aliases': find_dead_aliases(cfg),
        'wip_widgets': find_wip_widgets(cfg),
        'states': list_states(cfg),
        'datakeys': list_datakeys(cfg),
    }


def build_decisions(audits, audited_at):
    """Decisions pre-remplies (reviewed=False). nonprod->delete ; sinon clean + orphelins/alias morts."""
    dboards = {}
    for a in audits:
        if a['classification'] == 'nonprod':
            dboards[a['id']] = {'title': a['title'], 'action': 'delete'}
        else:
            wip_ids = {w['id'] for w in a['wip_widgets']}
            dboards[a['id']] = {
                'title': a['title'], 'action': 'clean',
                'expected_version': a['version'],
                'remove_widgets': [w for w in a['orphan_widgets'] if w not in wip_ids],
                'remove_aliases': list(a['dead_aliases']),
                'remove_states': [],
            }
    return {'reviewed': False, 'audited_at': audited_at, 'dashboards': dboards}


def render_report(audits):
    """Rapport Markdown lisible, groupe par dashboard, avec cases a cocher."""
    lines = ['# Audit dashboards — candidats de nettoyage', '',
             '> Editez `audit-decisions-*.json`, puis posez `"reviewed": true`.',
             '> Widgets `_wip` = signales seulement (jamais retires).', '']
    for a in sorted(audits, key=lambda x: (x['classification'] != 'nonprod', x['title'])):
        lines.append(f"## {a['title']}  `{(a['id'] or '')[:8]}`  v{a['version']}  [{a['classification']}]")
        c = a['counts']
        lines.append(f"widgets={c['widgets']} states={c['states']} aliases={c['aliases']}")
        if a['classification'] == 'nonprod':
            lines.append('')
            lines.append('- [ ] **SUPPRESSION COMPLETE** (export JSON ecrit avant DELETE)')
        else:
            wip_ids = {w['id'] for w in a['wip_widgets']}
            removable = [w for w in a['orphan_widgets'] if w not in wip_ids]
            if removable:
                lines.append(f"\n**Widgets orphelins ({len(removable)})** — retrait sur :")
                for wid in removable:
                    lines.append(f"- [ ] `{wid}`")
            if a['dead_aliases']:
                lines.append(f"\n**Alias morts ({len(a['dead_aliases'])})** :")
                for aid in a['dead_aliases']:
                    lines.append(f"- [ ] `{aid}`")
        if a['wip_widgets']:
            lines.append(f"\n**Widgets _wip ({len(a['wip_widgets'])}) — signales, NON retires** :")
            for w in a['wip_widgets']:
                lines.append(f"- {w['title']!r} `{w['id']}` ({w['fqn']})")
        if a['states']:
            lines.append('\n**States (inventaire — retrait manuel via remove_states)** :')
            for s in a['states']:
                tag = ' [root]' if s['root'] else ''
                lines.append(f"- `{s['id']}` {s['name']!r}{tag} — {s['widget_count']} widget(s)")
        if a['datakeys']:
            lines.append(f"\n**DataKeys referencees ({len(a['datakeys'])}) — inventaire informatif** :")
            seen = sorted({d['key_name'] for d in a['datakeys']})
            lines.append('  ' + ', '.join(f'`{k}`' for k in seen))
        lines.append('')
    return '\n'.join(lines)

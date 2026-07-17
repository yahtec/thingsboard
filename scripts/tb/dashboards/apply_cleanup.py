#!/usr/bin/env python3
"""Applique un fichier de decisions VALIDE (audit_dashboards.py) sur les dashboards du tenant.
Refuse tant que "reviewed": true n'est pas pose. Backup avant toute ecriture, controle de version.
Cf. spec 2026-07-17-nettoyage-dashboards-tenant.

Usage:
  python apply_cleanup.py --decisions audit-decisions-<ts>.json --token-file <p> [--dry-run] [--only delete|clean]
"""
import argparse, json, os, sys, time

import _lib_tb as tb
import dash_cleanup_lib as lib

_ACTIONS = {'delete', 'clean', 'skip'}


def validate_decisions(dec):
    """Leve ValueError si le fichier n'est pas valide/valide-humain. Rejet EN AMONT
    de toute ecriture reseau (evite un crash mi-batch = application partielle)."""
    if dec.get('reviewed') is not True:
        raise ValueError('decisions non validees : poser "reviewed": true apres relecture')
    dboards = dec.get('dashboards')
    if not isinstance(dboards, dict):
        raise ValueError('cle "dashboards" absente ou non-dict')
    for did, d in dboards.items():
        act = d.get('action')
        if act not in _ACTIONS:
            raise ValueError(f'action invalide pour {did}: {act!r} (attendu {_ACTIONS})')
        if not d.get('title'):
            raise ValueError(f'entree {did} sans "title"')
        if act == 'clean' and d.get('expected_version') is None:
            raise ValueError(f'clean {did} sans "expected_version" (controle de version requis)')


def resolve_token(args):
    if args.token_file:
        return tb.token_from_file(args.token_file)
    t = os.environ.get('TB_TOKEN')
    if not t:
        sys.exit('Fournir --token-file <path> ou definir TB_TOKEN')
    return t


def _safe(title):
    return ''.join(c if c.isalnum() else '-' for c in (title or 'dash'))[:40]


def do_delete(did, d, t, here, dry):
    full = tb.get_dashboard_by_id(did, t)
    ts = time.strftime('%Y%m%d-%H%M%S')
    exp = os.path.join(here, 'deleted', f"{_safe(d['title'])}-{did[:8]}-{ts}.json")
    tb.export_json(full, exp)
    print(f"  [delete] {d['title']!r} export -> {exp}")
    if dry:
        print('           (dry-run : DELETE non execute)')
        return
    tb.delete_dashboard(did, t)
    print('           DELETE OK')


def do_clean(did, d, t, here, dry):
    full = tb.get_dashboard_by_id(did, t)
    cur = full.get('version')
    exp_v = d.get('expected_version')
    if exp_v is not None and cur != exp_v:
        print(f"  [clean] {d['title']!r} ABORT : version prod={cur} != attendue={exp_v} (re-audite)")
        return
    ts = time.strftime('%Y%m%d-%H%M%S')
    bkp = os.path.join(here, f"backup-{_safe(d['title'])}-{did[:8]}.before_cleanup.{ts}.json")
    tb.export_json(full, bkp)
    rw, ra, rs = d.get('remove_widgets', []), d.get('remove_aliases', []), d.get('remove_states', [])
    print(f"  [clean] {d['title']!r} backup -> {bkp} ; retrait w={len(rw)} a={len(ra)} s={len(rs)}")
    if dry:
        print('          (dry-run : POST non execute)')
        return
    full['configuration'] = lib.remove_items(lib.get_config(full), rw, ra, rs)
    tb.post_dashboard(full, t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--decisions', required=True)
    ap.add_argument('--token-file')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--only', choices=['delete', 'clean'])
    args = ap.parse_args()

    try:
        with open(args.decisions, encoding='utf-8') as f:
            dec = json.load(f)
        validate_decisions(dec)
    except ValueError as e:
        sys.exit(f'decisions rejetees: {e}')
    t = resolve_token(args)
    here = os.path.dirname(os.path.abspath(__file__))

    for did, d in dec['dashboards'].items():
        act = d.get('action')
        if act == 'skip' or (args.only and act != args.only):
            continue
        if act == 'delete':
            do_delete(did, d, t, here, args.dry_run)
        elif act == 'clean':
            do_clean(did, d, t, here, args.dry_run)
    print('\ntermine' + (' (dry-run)' if args.dry_run else ''))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Audit LECTURE SEULE de tous les dashboards du tenant TSmart.
Produit un rapport Markdown + un fichier de decisions JSON (reviewed=False).
N'ecrit RIEN cote prod. Cf. spec 2026-07-17-nettoyage-dashboards-tenant.

Usage:
  python audit_dashboards.py --token-file <path>     # ou env TB_TOKEN
"""
import argparse, os, sys, time

import _lib_tb as tb
import dash_cleanup_lib as lib


def resolve_token(args):
    if args.token_file:
        return tb.token_from_file(args.token_file)
    t = os.environ.get('TB_TOKEN')
    if not t:
        sys.exit('Fournir --token-file <path> ou definir TB_TOKEN')
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token-file')
    args = ap.parse_args()
    t = resolve_token(args)

    metas = tb.list_tenant_dashboards(t)
    print(f'{len(metas)} dashboards dans le tenant')
    audits = []
    for m in metas:
        did = m['id']['id']
        full = tb.get_dashboard_by_id(did, t)
        a = lib.audit_dashboard(m, full)
        audits.append(a)
        print(f"  - {a['title']!r} [{a['classification']}] "
              f"orphelins={len(a['orphan_widgets'])} alias_morts={len(a['dead_aliases'])} "
              f"wip={len(a['wip_widgets'])}")

    ts = time.strftime('%Y%m%d-%H%M%S')
    here = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(here, f'audit-report-{ts}.md')
    dec_path = os.path.join(here, f'audit-decisions-{ts}.json')

    with open(report_path, 'wb') as f:
        f.write(lib.render_report(audits).encode('utf-8'))
    tb.export_json(lib.build_decisions(audits, time.strftime('%Y-%m-%dT%H:%M:%S')), dec_path)

    print(f'\nrapport   : {report_path}')
    print(f'decisions : {dec_path}')
    print('-> relire le rapport, editer le JSON, poser "reviewed": true, puis apply_cleanup.py')


if __name__ == '__main__':
    main()

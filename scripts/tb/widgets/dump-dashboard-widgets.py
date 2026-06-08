#!/usr/bin/env python3
"""
Dump tous les widgets utilises par un dashboard donne.

Usage:
  python scripts/tb/widgets/dump-dashboard-widgets.py --pwd <pwd> --dashboard "donnees_HP1"

- Login via API TB
- Cherche le dashboard par nom (textSearch)
- Recupere son JSON complet + le JSON de chaque widgetType reference
- Sauve tout dans scripts/tb/backup/widgets-tduo-v1/dump_<dashboard>_<ts>/
- Identifie les widgets "chart-like" et imprime un resume console

Pas de modification cote serveur. Lecture seule.
"""

import argparse, json, os, sys, time
import urllib.request, urllib.parse, urllib.error

BASE_URL = 'https://thingsboard.tsmart.fr'
BACKUP_DIR = os.path.join(os.path.dirname(__file__), '..', 'backup', 'widgets-tduo-v1')


def http_post(path, body, headers=None):
    headers = headers or {}
    headers.setdefault('Content-Type', 'application/json')
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def http_get(path, token):
    req = urllib.request.Request(BASE_URL + path, headers={'X-Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def login(user, pwd):
    return http_post('/api/auth/login', {'username': user, 'password': pwd})['token']


def find_dashboard(token, name):
    """Cherche dans tous les dashboards du tenant pour matcher exact ou substring."""
    q = urllib.parse.quote(name)
    res = http_get(f'/api/tenant/dashboards?pageSize=100&page=0&textSearch={q}', token)
    matches = res.get('data', [])
    if not matches:
        # Retry sans textSearch (au cas ou caracteres speciaux pertubent)
        all_res = http_get('/api/tenant/dashboards?pageSize=300&page=0', token)
        lower = name.lower()
        matches = [d for d in all_res.get('data', []) if lower in d['title'].lower()]
    return matches


def collect_widget_refs(dashboard_json):
    """Extrait la liste des (bundleAlias, typeAlias, widgetId) utilises dans le dashboard."""
    refs = []
    config = dashboard_json.get('configuration', {})
    widgets = config.get('widgets', {})
    if isinstance(widgets, dict):
        widget_iter = widgets.values()
    else:
        widget_iter = widgets
    for w in widget_iter:
        refs.append({
            'id': w.get('id'),
            'bundleAlias': w.get('bundleAlias'),
            'typeAlias': w.get('typeAlias'),
            'type': w.get('type'),  # latest, timeseries, control, ...
            'title': w.get('config', {}).get('title') or w.get('config', {}).get('name'),
            'widgetTypeId': w.get('widgetTypeId') or w.get('typeFullFqn'),
        })
    return refs


def fetch_widget_type_by_fqn(token, bundle_alias, type_alias):
    """Fetch widget type via fullFqn = bundleAlias.typeAlias."""
    fqn = f'{bundle_alias}.{type_alias}'
    # Endpoint TB 4.x : /api/widgetType?fullFqn=<fqn>
    try:
        return http_get(f'/api/widgetType?fullFqn={urllib.parse.quote(fqn)}', token)
    except urllib.error.HTTPError as e:
        # Fallback: certains TB exposent /api/widgetTypeInfo
        if e.code == 404:
            return None
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True, help='Password for API login')
    ap.add_argument('--dashboard', help='Dashboard title (substring OK). Omit with --list to just enumerate.')
    ap.add_argument('--list', action='store_true', help='List all dashboards and exit.')
    args = ap.parse_args()

    if not args.list and not args.dashboard:
        ap.error('--dashboard required unless --list given')

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime('%Y%m%d-%H%M%S')

    print(f'==> Login as {args.user} ...')
    token = login(args.user, args.pwd)
    print('    OK')

    if args.list:
        print('==> Listing all tenant dashboards ...')
        res = http_get('/api/tenant/dashboards?pageSize=500&page=0', token)
        for d in res.get('data', []):
            print(f'    {d["id"]["id"]} | {d["title"]}')
        print(f'    Total: {res.get("totalElements", 0)}')
        return

    print(f'==> Searching dashboard "{args.dashboard}" ...')
    matches = find_dashboard(token, args.dashboard)
    if not matches:
        sys.exit(f'No dashboard matches "{args.dashboard}".')
    if len(matches) > 1:
        print(f'    {len(matches)} matches found:')
        for m in matches:
            print(f'      {m["id"]["id"]} | {m["title"]}')
        # Prendre celui dont le titre matche le mieux (exact d'abord)
        exact = [m for m in matches if m['title'].lower() == args.dashboard.lower()]
        chosen = exact[0] if exact else matches[0]
        print(f'    -> using {chosen["title"]}')
    else:
        chosen = matches[0]
        print(f'    Found: {chosen["title"]} ({chosen["id"]["id"]})')

    print(f'==> Fetching full dashboard JSON ...')
    dash_id = chosen['id']['id']
    dash_full = http_get(f'/api/dashboard/{dash_id}', token)

    out_dir = os.path.join(BACKUP_DIR, f'dump_{ts}')
    os.makedirs(out_dir, exist_ok=True)

    dash_path = os.path.join(out_dir, 'dashboard.json')
    with open(dash_path, 'w', encoding='utf-8') as f:
        json.dump(dash_full, f, ensure_ascii=False, indent=2)
    print(f'    saved: {dash_path}')

    print(f'==> Collecting widget references ...')
    refs = collect_widget_refs(dash_full)
    print(f'    {len(refs)} widget instances found')

    # Dedupe par (bundleAlias, typeAlias)
    seen = {}
    for r in refs:
        key = (r.get('bundleAlias') or '', r.get('typeAlias') or '')
        if key not in seen:
            seen[key] = r
    print(f'    {len(seen)} distinct widget types referenced')

    print(f'==> Fetching each widget type definition ...')
    widget_types = []
    for (bundle, ttype), sample in seen.items():
        if not bundle or not ttype:
            continue
        try:
            wt = fetch_widget_type_by_fqn(token, bundle, ttype)
            if wt is None:
                print(f'    SKIP {bundle}.{ttype}: not found')
                continue
            slug = f'{bundle}__{ttype}'.replace('/', '_')
            wt_path = os.path.join(out_dir, f'widgettype__{slug}.json')
            with open(wt_path, 'w', encoding='utf-8') as f:
                json.dump(wt, f, ensure_ascii=False, indent=2)
            widget_types.append({'bundle': bundle, 'type': ttype, 'path': wt_path, 'name': wt.get('name')})
            print(f'    saved: {bundle}.{ttype} -> {wt_path}')
        except Exception as e:
            print(f'    ERROR {bundle}.{ttype}: {e}')

    # Resume console
    print('')
    print('==> Summary of widget instances in this dashboard:')
    for r in refs:
        print(f'    {r.get("type") or "?"} | {r.get("bundleAlias")}.{r.get("typeAlias")} | "{r.get("title")}"')

    print('')
    print(f'Dump complete in: {out_dir}')
    print('Send me the path or relevant widgettype__*.json files (especially any chart-like one) and I will write the patch.')


if __name__ == '__main__':
    main()

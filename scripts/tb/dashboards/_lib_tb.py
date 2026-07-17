#!/usr/bin/env python3
"""Helpers partages pour les scripts dashboard TB (login, GET, POST, backup)."""
import json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'donnees_HP1'

def login(user, pwd):
    b = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']

def token_or_login(user, pwd):
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if not pwd:
        sys.exit('Fournir --pwd ou definir TB_TOKEN')
    return login(user, pwd)

def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    try:
        with urllib.request.urlopen(r, timeout=60) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'GET {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def get_dashboard(t):
    return http_get(f'/api/dashboard/{DASHBOARD_ID}', t)

def backup(dash, tag):
    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')
    path = os.path.join(here, f'backup-mes-installations.before_{tag}.{ts}.json')
    with open(path, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {path}')
    return path

def post_dashboard(dash, t):
    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')
    return resp

# ---------- helpers generiques (nettoyage multi-dashboards, 2026-07-17) ----------

def http_delete(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}',
        headers={'X-Authorization': f'Bearer {t}'}, method='DELETE')
    try:
        with urllib.request.urlopen(r, timeout=120) as o:
            body = o.read().decode('utf-8')
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f'DELETE {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def list_tenant_dashboards(t):
    """Depagine /api/tenant/dashboards -> liste de DashboardInfo."""
    out, page = [], 0
    while True:
        d = http_get(f'/api/tenant/dashboards?pageSize=100&page={page}', t)
        out += d.get('data', [])
        if not d.get('hasNext'):
            return out
        page += 1

def get_dashboard_by_id(did, t):
    return http_get(f'/api/dashboard/{did}', t)

def delete_dashboard(did, t):
    return http_delete(f'/api/dashboard/{did}', t)

def export_json(obj, path):
    """Ecrit obj en JSON UTF-8 (indent=1), cree les dossiers parents. Retourne path."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1).encode('utf-8'))
    return path

def token_from_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read().strip()

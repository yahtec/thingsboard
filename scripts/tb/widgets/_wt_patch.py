#!/usr/bin/env python3
"""Helpers pour patcher les widget_types tenant.tsmart.* par fqn (GET/modif/POST).

Modele : les widgets a fqn pointe (tenant.tsmart.X) N'APPARAISSENT PAS dans
/api/widgetTypes -> on les recupere par ?fqn= et on POST avec updateExistingByFqn=true.
"""
import json, os, sys, time, urllib.request, urllib.error

BASE_URL = 'https://thingsboard.tsmart.fr'
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backup', 'widgets-tduo-v1')


def _login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode('utf-8'))['token']


def token_or_login(user, pwd):
    """Ordre de priorite : TB_TOKEN (env) > --pwd > TB_USER+TB_PASS (env). Le dernier
    cas permet de lire les identifiants du compte de service svc-tbnotify@yahtec.com
    (TENANT_ADMIN) depuis le fichier .env de prod, via scripts/tb/gas/creds-from-server.sh
    -- aucun mot de passe n'apparait alors jamais dans une ligne de commande."""
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if pwd:
        return _login(user, pwd)
    env_user, env_pwd = os.environ.get('TB_USER'), os.environ.get('TB_PASS')
    if env_user and env_pwd:
        return _login(env_user, env_pwd)
    sys.exit('Fournir TB_TOKEN (env), --pwd, ou TB_USER+TB_PASS (env)')


def _get(path, tok):
    r = urllib.request.Request(f'{BASE_URL}{path}', headers={'X-Authorization': f'Bearer {tok}'})
    try:
        with urllib.request.urlopen(r, timeout=60) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'GET {path} -> HTTP {e.code}: {e.read().decode("utf-8", "replace")[:400]}')


def _post(path, body, tok):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{path}', data=data,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {tok}'},
        method='POST')
    try:
        with urllib.request.urlopen(r, timeout=120) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {path} -> HTTP {e.code}: {e.read().decode("utf-8", "replace")[:400]}')


def get_widget_by_fqn(fqn, tok):
    return _get(f'/api/widgetType?fqn={fqn}', tok)


def post_widget(w, tok):
    return _post('/api/widgetType?updateExistingByFqn=true', w, tok)


def backup(obj, tag):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    p = os.path.join(BACKUP_DIR, f'{tag}.{time.strftime("%Y%m%d-%H%M%S")}.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f'  backup: {p}')
    return p


def apply_replacements(cs, replacements):
    """replacements: [(name, OLD, NEW)]. Chaque OLD doit apparaitre exactement 1x."""
    new = cs
    for name, old, rep in replacements:
        nn = new.count(old)
        if nn != 1:
            sys.exit(f'  [{name}] ancre {nn}x (attendu 1) -- source live a change')
        new = new.replace(old, rep, 1)
        print(f'  [{name}] OK (+{len(rep) - len(old)}c)')
    return new

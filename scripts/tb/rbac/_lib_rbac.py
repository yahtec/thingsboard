#!/usr/bin/env python3
"""Helpers RBAC portefeuilles : provisioning idempotent (customers, devices, users, relations).

Pattern repris de scripts/tb/dashboards/_lib_tb.py (urllib stdlib, X-Authorization Bearer).
Toutes les fonctions ensure_* / assign_* prennent un flag `apply` : si False (dry-run),
elles font UNIQUEMENT des GET (lecture seule) et loguent l'action qu'elles feraient.

Le role RBAC est ecrit dans User.additionalInfo['portfolioRole'] (source lue par le
backend AccessScopeService via UserAuthDetailsCache, et par le frontend YahtecRoleService).
Relations portefeuille : type 'CanView' (partie -> site) / 'Excluded' (staff -> site),
typeGroup 'COMMON', from = customer-partie, to = customer-site.
"""
import json, os, sys, urllib.parse, urllib.request, urllib.error

BASE_URL = os.environ.get('TB_BASE_URL', 'https://thingsboard.tsmart.fr')

CANVIEW = 'CanView'
EXCLUDED = 'Excluded'
COMMON = 'COMMON'


def login(user, pwd):
    b = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode('utf-8'))['token']


def token_or_login(user, pwd):
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if not pwd:
        sys.exit('Fournir --pwd ou definir TB_TOKEN')
    return login(user, pwd)


def _req(method, p, t, body=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    headers = {'X-Authorization': f'Bearer {t}'}
    if data is not None:
        headers['Content-Type'] = 'application/json; charset=utf-8'
    return urllib.request.Request(f'{BASE_URL}{p}', data=data, headers=headers, method=method)


def http_get(p, t, allow_404=False):
    try:
        with urllib.request.urlopen(_req('GET', p, t), timeout=60) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        sys.exit(f'GET {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:400]}')


def http_post(p, b, t):
    try:
        with urllib.request.urlopen(_req('POST', p, t, b), timeout=120) as o:
            raw = o.read().decode('utf-8')
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:400]}')


def http_delete(p, t):
    try:
        with urllib.request.urlopen(_req('DELETE', p, t), timeout=60) as o:
            return o.status
    except urllib.error.HTTPError as e:
        sys.exit(f'DELETE {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:400]}')


def _q(**kw):
    return urllib.parse.urlencode({k: v for k, v in kw.items() if v is not None})


# ---------- Customers ----------

def find_customer_by_title(t, title):
    """Cherche un customer par titre exact (via la liste tenant, filtre client-side)."""
    page = http_get(f'/api/customers?{_q(pageSize=500, page=0, textSearch=title)}', t)
    for c in (page or {}).get('data', []):
        if c.get('title') == title:
            return c
    return None


def ensure_customer(t, title, apply):
    c = find_customer_by_title(t, title)
    if c:
        print(f'  customer OK       : {title} ({c["id"]["id"]})')
        return c['id']['id']
    if not apply:
        print(f'  [DRY] creerait customer : {title}')
        return None
    c = http_post('/api/customer', {'title': title}, t)
    print(f'  customer CREE     : {title} ({c["id"]["id"]})')
    return c['id']['id']


# ---------- Devices ----------

def find_device_by_name(t, name):
    return http_get(f'/api/tenant/devices?{_q(deviceName=name)}', t, allow_404=True)


def assign_device_to_customer(t, device_id, customer_id, apply):
    if not apply:
        print(f'  [DRY] assignerait device {device_id} -> customer {customer_id}')
        return
    http_post(f'/api/customer/{customer_id}/device/{device_id}', {}, t)
    print(f'  device ASSIGNE    : {device_id} -> customer {customer_id}')


# ---------- Users ----------

def find_user_by_email(t, email):
    page = http_get(f'/api/users?{_q(pageSize=500, page=0, textSearch=email)}', t)
    for u in (page or {}).get('data', []):
        if u.get('email') == email:
            return u
    return None


def _set_role(user_obj, role):
    info = dict(user_obj.get('additionalInfo') or {})
    info['portfolioRole'] = role
    user_obj['additionalInfo'] = info
    return user_obj


def ensure_user(t, email, authority, customer_id, role, password, apply):
    """Cree (si absent) un user avec additionalInfo.portfolioRole ; sinon met a jour le role.
    authority = 'CUSTOMER_USER' (customer_id requis) ou 'TENANT_ADMIN' (customer_id=None).
    """
    u = find_user_by_email(t, email)
    if u:
        current = (u.get('additionalInfo') or {}).get('portfolioRole')
        if current == role:
            print(f'  user OK           : {email} (role={role})')
            return u['id']['id']
        if not apply:
            print(f'  [DRY] MAJ role user : {email} {current!r} -> {role!r}')
            return u['id']['id']
        http_post('/api/user', _set_role(u, role), t)
        print(f'  user role MAJ     : {email} -> {role}')
        return u['id']['id']
    if not apply:
        print(f'  [DRY] creerait user : {email} authority={authority} role={role}'
              + ('' if customer_id else ' (tenant admin)'))
        return None
    body = {'email': email, 'authority': authority, 'additionalInfo': {'portfolioRole': role}}
    if customer_id:
        body['customerId'] = {'id': customer_id, 'entityType': 'CUSTOMER'}
    created = http_post('/api/user?sendActivationMail=false', body, t)
    uid = created['id']['id']
    if password:
        link = http_get(f'/api/user/{uid}/activationLink', t)  # renvoie l'URL avec activateToken
        tok = urllib.parse.parse_qs(urllib.parse.urlparse(str(link)).query).get('activateToken', [None])[0]
        if tok:
            http_post('/api/noauth/activate?sendActivationMail=false', {'activateToken': tok, 'password': password}, t)
            print(f'  user CREE+ACTIVE  : {email} (role={role})')
        else:
            print(f'  user CREE (activation manuelle requise, lien: {link}) : {email}')
    else:
        print(f'  user CREE (sans mdp) : {email}')
    return uid


# ---------- Relations ----------

def relation_exists(t, from_id, to_id, rel_type):
    p = f'/api/relation?{_q(fromId=from_id, fromType="CUSTOMER", relationType=rel_type, relationTypeGroup=COMMON, toId=to_id, toType="CUSTOMER")}'
    return http_get(p, t, allow_404=True) is not None


def ensure_relation(t, from_cust_id, to_cust_id, rel_type, apply):
    if relation_exists(t, from_cust_id, to_cust_id, rel_type):
        print(f'  relation OK       : {from_cust_id} -{rel_type}-> {to_cust_id}')
        return
    if not apply:
        print(f'  [DRY] creerait relation : {from_cust_id} -{rel_type}-> {to_cust_id}')
        return
    body = {'from': {'id': from_cust_id, 'entityType': 'CUSTOMER'},
            'to': {'id': to_cust_id, 'entityType': 'CUSTOMER'},
            'type': rel_type, 'typeGroup': COMMON}
    http_post('/api/relation', body, t)
    print(f'  relation CREE     : {from_cust_id} -{rel_type}-> {to_cust_id}')

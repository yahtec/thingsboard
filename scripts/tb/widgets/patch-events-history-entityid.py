#!/usr/bin/env python3
"""
Patch events_history widget : ajoute entityId={id, entityType} en plus de
deviceId dans les params openState. Necessaire pour que l'entity alias
'Chaufferie selectionnee' (stateEntity, stateEntityParamName=null) puisse
resoudre le device du dashboard cible fault_diagnostic.

Sans cela, l'alias fallback sur defaultStateEntity (9df09950-... qui
n'existe pas) -> datasource pac_v2 vide -> TB framework affiche
'Aucune donnee a afficher sur le widget'.

Idempotent via marker __EVTHIST_ENTITYID_PATCH__.
"""

import argparse, json, sys, time, urllib.request, urllib.error

WIDGET_ID = 'af86baf0-3fe1-11f1-bbfe-e1395562cba0'
BASE_URL  = 'https://thingsboard.tsmart.fr'
MARKER    = '__EVTHIST_ENTITYID_PATCH__'

OLD = """        var params = {
            deviceId: devId,"""

NEW = """        var params = {
            // """ + MARKER + """ : entityId nested pour resolution alias 'Chaufferie selectionnee'
            entityId: { id: devId, entityType: 'DEVICE' },
            deviceId: devId,"""


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o: return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o: return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()
    t = login(args.user, args.pwd)
    w = http_get(f'/api/widgetType/{WIDGET_ID}', t)
    print(f'Widget v{w.get("version")}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/backup/widgets-tduo-v1/events_history.before_entityid.{ts}.json','wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Already patched')
        return
    if OLD not in cs:
        sys.exit('OLD pattern not found')
    w['descriptor']['controllerScript'] = cs.replace(OLD, NEW, 1)
    resp = http_post('/api/widgetType', w, t)
    print(f'Posted v{resp.get("version")}')


if __name__ == '__main__': main()

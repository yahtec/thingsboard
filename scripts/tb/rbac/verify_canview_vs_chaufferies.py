#!/usr/bin/env python3
"""Re-verifie CanView==chaufferies par PARTY (garde-fou #4) + backup des configs dashboard.
Lecture seule cote TB. Exit non-zero si un PARTY a un desaccord (bloque le chantier)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import _lib_rbac as tb

YAHTEC = '2e521d10-3e5d-11f1-bbfe-e1395562cba0'
DASHBOARDS = ['0964da30-3e56-11f1-bbfe-e1395562cba0', '4aa4ccd0-422a-11f1-bbfe-e1395562cba0']
BACKUP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                          'scratchpad', 'chantier4-backup')

def canview_site_ids(t, party_cid):
    p = f'/api/relations?fromId={party_cid}&fromType=CUSTOMER'
    rels = tb.http_get(p, t) or []
    return {r['to']['id'] for r in rels
            if r.get('type') == 'CanView' and r.get('typeGroup') == 'COMMON'}

def main():
    t = tb.token_or_login(os.environ.get('TB_USER', 'je@yahtec.com'), os.environ.get('TB_PWD'))
    # map site_customer_id -> device pour resoudre les noms
    devs = tb.http_get('/api/tenant/devices?pageSize=1000&page=0&type=pac%20hybride', t)['data']
    dev_by_id = {d['id']['id']: d['name'] for d in devs}
    site_of_dev = {}
    for d in devs:
        attrs = tb.http_get(f"/api/plugins/telemetry/DEVICE/{d['id']['id']}/values/attributes/SERVER_SCOPE?keys=site_customer_id", t) or []
        sc = next((a['value'] for a in attrs if a['key'] == 'site_customer_id'), None)
        if sc:
            site_of_dev[d['id']['id']] = sc
    users = tb.http_get('/api/users?pageSize=1000&page=0', t)['data']
    ok = True
    for u in users:
        ai = u.get('additionalInfo') or {}
        if u.get('authority') != 'CUSTOMER_USER' or (u.get('customerId') or {}).get('id') in (None, YAHTEC):
            continue
        uid = u['id']['id']; party_cid = u['customerId']['id']
        attrs = tb.http_get(f'/api/plugins/telemetry/USER/{uid}/values/attributes/SERVER_SCOPE?keys=chaufferies', t) or []
        raw = next((a['value'] for a in attrs if a['key'] == 'chaufferies'), None)
        if raw is None:
            # I14 : la migration (chantier #4) supprime volontairement cet attribut
            # (bascule CanView-only). Attribut absent = migre, PAS un desaccord.
            # Ne compte ni ne diverge : seul un attribut EXISTANT et divergent est un vrai defaut.
            print(f'  {u["email"]:32} attribut chaufferies absent (migre CanView-only) -> skip')
            continue
        attr_ids = set(json.loads(raw) if isinstance(raw, str) else (raw or []))
        cv_sites = canview_site_ids(t, party_cid)
        cv_ids = {did for did, sc in site_of_dev.items() if sc in cv_sites}
        same = attr_ids == cv_ids
        ok = ok and same
        mark = 'OK' if same else '!!! DESACCORD'
        print(f'  {u["email"]:32} attr={sorted(dev_by_id.get(i, i) for i in attr_ids)} '
              f'canview={sorted(dev_by_id.get(i, i) for i in cv_ids)} -> {mark}')
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for did in DASHBOARDS:
        d = tb.http_get(f'/api/dashboard/{did}', t)
        path = os.path.join(BACKUP_DIR, f'dash-{did[:8]}.json')
        open(path, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=1))
        print(f'  backup {did[:8]} -> {path}')
    sys.exit(0 if ok else 2)

if __name__ == '__main__':
    main()

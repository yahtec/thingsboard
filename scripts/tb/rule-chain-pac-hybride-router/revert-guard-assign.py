#!/usr/bin/env python3
"""Revert de guard-assign-node.py : rebranche originator --Success--> Assign to Yahtec
et deconnecte le filtre 'Provisionnee ?' + 'load site_assigned' (laisses orphelins,
sans remaniement d'index). Idempotent. Dry-run par defaut ; --apply pour ecrire."""
import argparse, os, sys, time, json, urllib.request, urllib.error

RC_ID = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
BASE_URL = os.environ.get('TB_BASE_URL', 'https://thingsboard.tsmart.fr')
ORIG, SAVE, ASSIGN = 'originator -> device(${id})', 'save TS (per-id device)', 'Assign to Yahtec'
GETATTR, FILTER = 'load site_assigned', 'Provisionnee ?'


def _req(method, p, t, body=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    h = {'X-Authorization': f'Bearer {t}'}
    if data is not None:
        h['Content-Type'] = 'application/json; charset=utf-8'
    return urllib.request.Request(f'{BASE_URL}{p}', data=data, headers=h, method=method)


def http_get(p, t):
    with urllib.request.urlopen(_req('GET', p, t), timeout=60) as o:
        return json.loads(o.read().decode('utf-8'))


def http_post(p, b, t):
    try:
        with urllib.request.urlopen(_req('POST', p, t, b), timeout=120) as o:
            raw = o.read().decode('utf-8')
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def token_or_login(user, pwd):
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if not pwd:
        sys.exit('Fournir --pwd ou definir TB_TOKEN')
    b = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com'); ap.add_argument('--pwd', default=None)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    t = token_or_login(args.user, args.pwd)
    meta = http_get(f'/api/ruleChain/{RC_ID}/metadata', t)
    nodes, conns = meta['nodes'], meta['connections']
    idx = {n['name']: i for i, n in enumerate(nodes)}
    if FILTER not in idx:
        print('garde absente -> rien a revert'); return
    orig_i, assign_i = idx[ORIG], idx[ASSIGN]
    getattr_i, filter_i = idx.get(GETATTR), idx[FILTER]
    # retirer toutes les aretes touchant la garde, rebrancher orig->assign
    drop = {getattr_i, filter_i}
    new_conns = [c for c in conns if c['fromIndex'] not in drop and c['toIndex'] not in drop]
    new_conns = [c for c in new_conns
                 if not (c['fromIndex'] == orig_i and c['toIndex'] == getattr_i)]
    new_conns.append({'fromIndex': orig_i, 'toIndex': assign_i, 'type': 'Success'})
    meta['connections'] = new_conns
    print(f'revert: {ORIG} --Success--> {ASSIGN} ; garde {GETATTR}/{FILTER} orphelinee')
    if not args.apply:
        print('[DRY-RUN]'); return
    ts = time.strftime('%Y%m%d-%H%M%S')
    bpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup', f'metadata.before_revert.{ts}.json')
    with open(bpath, 'wb') as f:
        f.write(json.dumps(http_get(f'/api/ruleChain/{RC_ID}/metadata', t), ensure_ascii=False, indent=2).encode('utf-8'))
    http_post('/api/ruleChain/metadata', meta, t)
    print(f'OK revert (backup {bpath})')

if __name__ == '__main__':
    main()

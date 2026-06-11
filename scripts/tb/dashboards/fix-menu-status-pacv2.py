#!/usr/bin/env python3
"""
Corrige les macarons d'etat de la page menu (liste des chaufferies).

Probleme : le widget menu (HTML Value Card 77e3ece4) colore le macaron d'apres
la cle time-series flat HP1_status, qui n'est plus alimentee depuis la coupure
de la branche flat (~2026-05-29). Les valeurs latest sont figees (bureaux : 4
-> orange) ou absentes (Serris -> gris), et le mapping etait de toute facon
errone (6 = vert alors que dans pac_v2, HP.status 6 = defaut).

Fix : la query entitiesQuery demande pac_v2 au lieu de HP1_status, et
statusMeta() derive l'etat de pac_v2 + fraicheur du ts :
  - gris  "Hors ligne" : pas de pac_v2, ts plus vieux que 15 min, ou comm=false
  - rouge "Défaut"     : HP.status==6 ou boil.status>=40
  - vert  "En marche"  : compresseur/chaudiere actifs (freq, rpm, status 5/30)
  - vert  "Veille"     : comm OK, sans defaut, a l'arret

Idempotent : marker __MENU_STATUS_PACV2_V1__ dans le cardHtml.

Usage:
  fix-menu-status-pacv2.py --pwd <pwd> [--dry-run]
  TB_TOKEN=... fix-menu-status-pacv2.py [--dry-run]
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
WID_MENU     = '77e3ece4-32d7-80d8-22b5-a0ff8a74caff'
MARKER       = '__MENU_STATUS_PACV2_V1__'


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}',
        headers={'X-Authorization': f'Bearer {t}'}, method='GET')
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


def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def must_replace(s, old, new, label, count=1):
    n = s.count(old)
    if n != count:
        sys.exit(f'[{label}] anchor trouve {n} fois (attendu {count}) : {old[:80]!r}')
    return s.replace(old, new, count)


OLD_STATUSMETA = """  function statusMeta(s) {
    if (s === 6)   return { color: '#43a047', label: 'En service' };
    if (s === 0)   return { color: '#e53935', label: 'Arrêt' };
    if (s == null) return { color: '#9e9e9e', label: 'Inconnu' };
    return         { color: '#fb8c00', label: 'Attention' };
  }"""

NEW_STATUSMETA = """  /* __MENU_STATUS_PACV2_V1__ : macaron derive de pac_v2 (la cle flat
     HP1_status n'est plus alimentee depuis la coupure de la branche flat).
     gris = hors ligne (pas de pac_v2 frais ou comm=false), rouge = defaut,
     vert = comm OK sans defaut (En marche / Veille). */
  var OFFLINE_MS = 15 * 60 * 1000; // regime live = 1 msg/min
  function statusMeta(ts) {
    var GRIS = { color: '#9e9e9e', label: 'Hors ligne' };
    var cell = ts && ts.pac_v2;
    if (!cell || cell.value == null || cell.value === '') return GRIS;
    if (Number(cell.ts || 0) && (Date.now() - Number(cell.ts)) > OFFLINE_MS) return GRIS;
    var p = cell.value;
    if (typeof p === 'string') { try { p = JSON.parse(p); } catch (e) { return GRIS; } }
    var hps = (p && p.HPs) || [];
    var comm = false, fault = false, running = false;
    for (var i = 0; i < hps.length; i++) {
      var hp = hps[i] || {};
      if (hp.comm !== true && hp.comm !== 'true') continue;
      comm = true;
      var H = hp.HP || {}, inv = hp.invert || {}, boil = hp.boil || {};
      if (Number(H.status) === 6 || Number(boil.status || 0) >= 40) fault = true;
      if (Number(inv.freq || 0) > 1 || Number(H.rpm || 0) > 10 ||
          Number(boil.rpm || 0) > 10 || Number(boil.status) === 5 ||
          Number(boil.status) === 30) running = true;
    }
    if (!comm) return GRIS;
    if (fault) return { color: '#e53935', label: 'Défaut' };
    if (running) return { color: '#43a047', label: 'En marche' };
    return { color: '#43a047', label: 'Veille' };
  }"""

OLD_QUERY_KEY = "{ type: 'TIME_SERIES', key: 'HP1_status' }"
NEW_QUERY_KEY = "{ type: 'TIME_SERIES', key: 'pac_v2' }"

OLD_USAGE = """        var stRaw = ts.HP1_status && ts.HP1_status.value;
        var st    = stRaw === '' || stRaw == null ? null : parseInt(stRaw, 10);
        var sm    = statusMeta(st);"""

NEW_USAGE = """        var sm    = statusMeta(ts);"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = os.environ.get('TB_TOKEN')
    if not t:
        if not args.pwd:
            sys.exit('Fournir --pwd ou definir TB_TOKEN')
        t = login(args.user, args.pwd)

    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    widgets = dash['configuration']['widgets']
    if WID_MENU not in widgets:
        sys.exit(f'widget menu absent : {WID_MENU}')

    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'backup-mes-installations.before_menu_status.{ts}.json')
    with open(bak, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {bak}')

    html = widgets[WID_MENU]['config']['settings']['cardHtml']
    if MARKER in html:
        print('deja patche (skip idempotent)')
        return

    html = must_replace(html, OLD_STATUSMETA, NEW_STATUSMETA, 'statusMeta')
    html = must_replace(html, OLD_QUERY_KEY, NEW_QUERY_KEY, 'query latestValues')
    html = must_replace(html, OLD_USAGE, NEW_USAGE, 'usage statusMeta')
    widgets[WID_MENU]['config']['settings']['cardHtml'] = html
    print('cardHtml patche (3 remplacements)')

    if args.dry_run:
        prev = bak.replace('.before_menu_status.', '.preview_menu_status.')
        with open(prev, 'wb') as f:
            f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] pas de POST. Preview: {prev}')
        return

    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')


if __name__ == '__main__':
    main()

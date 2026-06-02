#!/usr/bin/env python3
"""
Patch le widget tduo.fault_diagnostic (id 5e6e2180-478e-...) pour parser les
arrays str_v dans _fetchRealtime (comme _fetchSnapshot le fait deja).

Avant : Number(p.value) -> NaN sur "[v1,v2,...]" -> filter elimine tout
Apres : parse JSON array, etaler les N points temporellement sur la fenetre
        [evtTs - 180s, evtTs + 30s] (spec user : 3 min avant + 30 s apres)

Idempotent via marker __FAULT_DIAG_ARRAY_PATCH__.

Usage:
  patch-fault-diag-array-parse.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

WIDGET_ID = '5e6e2180-478e-11f1-a9c9-47ea18512754'
BASE_URL  = 'https://thingsboard.tsmart.fr'
MARKER    = '__FAULT_DIAG_ARRAY_PATCH__'

OLD_BLOCK = """      .then(function(raw){
          var series = {};
          for (var k in raw){
              var pts = (raw[k]||[]).map(function(p){return {ts:p.ts,v:Number(p.value)};})
                  .filter(function(p){return !isNaN(p.v) && p.v > -99;})
                  .sort(function(a,b){return a.ts - b.ts;});
              if (pts.length) series[k] = pts;
          }
          self._rtSeries = series;
          self._pfx = pfx;
          self._renderRealtime();
      })"""

NEW_BLOCK = """      .then(function(raw){
          // """ + MARKER + """ : expand arrays str_v -> N points temporels
          // Spec user : N valeurs etalees sur [evtTs - 180s, evtTs + 30s]
          // (3 min avant defaut + 30 s apres). 1 valeur = scalar a evtTs.
          var series = {};
          var WIN_BEFORE_MS = 180000;
          var WIN_AFTER_MS  = 30000;
          var SEND_DELAY_MS = 30000;
          var SPAN_MS = WIN_BEFORE_MS + WIN_AFTER_MS;
          for (var k in raw){
              var pts = [];
              (raw[k]||[]).forEach(function(p){
                  var rv = p.value;
                  var arr;
                  try {
                      if (typeof rv === 'string' && rv.charAt(0) === '[') {
                          arr = JSON.parse(rv);
                      } else if (Array.isArray(rv)) {
                          arr = rv;
                      } else {
                          arr = [Number(rv)];
                      }
                  } catch(e) { arr = [Number(rv)]; }
                  if (!Array.isArray(arr) || !arr.length) return;
                  var anchor = (c.evtTs && c.evtTs > 0) ? c.evtTs : (p.ts - SEND_DELAY_MS);
                  var n = arr.length;
                  if (n === 1) {
                      var v0 = Number(arr[0]);
                      if (!isNaN(v0) && v0 > -99) pts.push({ts: anchor, v: v0});
                      return;
                  }
                  var step = SPAN_MS / (n - 1);
                  for (var i = 0; i < n; i++) {
                      var v = Number(arr[i]);
                      if (isNaN(v) || v <= -99) continue;
                      pts.push({ts: (anchor - WIN_BEFORE_MS) + i * step, v: v});
                  }
              });
              pts.sort(function(a,b){return a.ts - b.ts;});
              if (pts.length) series[k] = pts;
          }
          self._rtSeries = series;
          self._pfx = pfx;
          self._renderRealtime();
      })"""


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
    print(f'Widget: {w["name"]} ({w["fqn"]}) v{w.get("version","?")}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/backup/widgets-tduo-v1/fault_diagnostic.before_array_patch.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Already patched (idempotent skip)')
        return
    if OLD_BLOCK not in cs:
        sys.exit('OLD_BLOCK pattern not found -- widget code may have changed')
    new_cs = cs.replace(OLD_BLOCK, NEW_BLOCK, 1)
    w['descriptor']['controllerScript'] = new_cs
    print(f'  controllerScript: {len(cs)} -> {len(new_cs)} chars (+{len(new_cs)-len(cs)})')
    resp = http_post('/api/widgetType', w, t)
    print(f'Posted OK. New version: {resp.get("version","?")}')


if __name__ == '__main__':
    main()

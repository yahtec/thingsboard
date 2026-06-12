#!/usr/bin/env python3
"""
Patch events_history widget : masque l'icone "Voir diagnostic" quand aucun
snapshot n'existe pour le defaut.

1) Regle statique (cas surs, zero requete) :
   - evt_device 60-68 (unites module) : jamais de snapshot d'office
     (confirme en prod : 36 evenements, 0 snapshot)
   - evt_device 50-55 (PAC Hybride) + evt_fault communication {15,29,38,39,40}
     (fault 88 exclu de la liste : un cas prod avec snapshot -> probe dynamique)
2) Probe dynamique : 1 requete telemetrie sur les 8 cles snapshot du diagnostic
   (p_bp, p_hp, t_bp, t_hph, wp_b, b_s, pb_spd, pe_spd) couvrant la fenetre des
   evenements charges ; icone visible ssi un ts snapshot existe dans
   [anchor - 120 s, anchor + 60 s] (meme fenetre que fault_diagnostic).
3) Premier rendu sans icones (probe en cours) ; en cas d'echec du probe, repli
   sur la regle statique seule (icones affichees pour les non-exclus).

Spec : docs/superpowers/specs/2026-06-12-events-history-hide-no-snapshot-design.md
Idempotent via marker __EVTHIST_NOSNAP_PATCH__.

Usage:
  patch-events-history-hide-no-snapshot.py --pwd <pwd> [--dry-run]
"""

import argparse, json, sys, time, urllib.request, urllib.error

WIDGET_ID = 'af86baf0-3fe1-11f1-bbfe-e1395562cba0'
BASE_URL  = 'https://thingsboard.tsmart.fr'
MARKER    = '__EVTHIST_NOSNAP_PATCH__'

# --- Remplacement 1 : helpers + garde dans _actionCell ----------------------

OLD_ACTION = """self._actionCell = function(rec) {
    // Bouton visible sur tout évènement avec un code défaut, qu'il soit actif, résolu ou standalone.
    if (!rec.fault) return '';
    if (rec.type !== 1 && rec.type !== 4) return '';"""

NEW_ACTION = """self._noSnapStatic = function(rec) {
    // """ + MARKER + """ : cas surs sans snapshot (regle statique)
    // - unites module (60-68) : jamais de snapshot d'office
    // - PAC Hybride (50-55) + defaut communication : PAC injoignable
    //   (88 absent de la liste : cas prod avec snapshot -> probe dynamique)
    var COMM_FAULTS = {15:1,29:1,38:1,39:1,40:1};
    if (rec.device >= 60 && rec.device <= 68) return true;
    if (rec.device >= 50 && rec.device <= 55 && COMM_FAULTS[rec.fault]) return true;
    return false;
};

self._snapAnchor = function(rec) {
    return rec.appearTs || rec.resolvedTs || rec.ts;
};

self._hasSnap = function(rec) {
    // _snapTsList : undefined = probe en cours (pas d'icone),
    // null = probe en echec (repli : icone affichee), array = ts des snapshots
    if (self._snapTsList === null) return true;
    if (!self._snapTsList) return false;
    var a = self._snapAnchor(rec);
    for (var i = 0; i < self._snapTsList.length; i++) {
        var t = self._snapTsList[i];
        if (t >= a - 120000 && t <= a + 60000) return true;
        if (t > a + 60000) break;
    }
    return false;
};

self._actionCell = function(rec) {
    // Bouton visible seulement si un snapshot existe pour ce defaut
    // (invariant : icone visible <=> la page diagnostic trouvera un snapshot).
    if (!rec.fault) return '';
    if (rec.type !== 1 && rec.type !== 4) return '';
    if (self._noSnapStatic(rec)) return '';
    if (!self._hasSnap(rec)) return '';"""

# --- Remplacement 2 : probe dans onDataUpdated -------------------------------

OLD_UPDATE = """self.onDataUpdated = function() {
    var raw = self._collect();
    self._rows = self._pair(raw);
    self._render();
};"""

NEW_UPDATE = """// """ + MARKER + """ : probe snapshots — 1 requete pour toute la fenetre
var SNAP_PROBE_KEYS = ['p_bp','p_hp','t_bp','t_hph','wp_b','b_s','pb_spd','pe_spd'];

self._probeSnapshots = function() {
    var cand = self._rows.filter(function(r){
        return r.fault && (r.type === 1 || r.type === 4) && !self._noSnapStatic(r);
    });
    if (!cand.length) { self._probeRange = null; self._snapTsList = []; return; }
    var anchors = cand.map(self._snapAnchor);
    var minTs = Math.min.apply(null, anchors) - 120000;
    var maxTs = Math.max.apply(null, anchors) + 60000;
    var rangeKey = minTs + '|' + maxTs;
    if (self._probeRange === rangeKey) return; // cache : fenetre inchangee
    self._probeRange = rangeKey;
    self._snapTsList = undefined; // probe en cours -> pas d'icones
    var devId = null;
    try {
        var ds = self.ctx.datasources && self.ctx.datasources[0];
        if (ds && ds.entityId) devId = ds.entityId;
        else if (ds && ds.entity && ds.entity.id) devId = ds.entity.id.id;
    } catch(_){}
    var tok = localStorage.getItem('jwt_token');
    if (!devId || !tok) { self._probeRange = null; self._snapTsList = null; return; }
    var url = '/api/plugins/telemetry/DEVICE/' + devId + '/values/timeseries?keys=' +
              SNAP_PROBE_KEYS.join(',') + '&startTs=' + minTs + '&endTs=' + maxTs +
              '&limit=1000&agg=NONE';
    fetch(url, { headers:{'X-Authorization':'Bearer '+tok} })
      .then(function(r){ if (!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
      .then(function(data){
          if (self._probeRange !== rangeKey) return; // fenetre changee entre-temps
          var seen = {}, list = [], truncated = false;
          SNAP_PROBE_KEYS.forEach(function(k){
              var arr = data[k] || [];
              if (arr.length >= 1000) truncated = true;
              arr.forEach(function(p){
                  if (!seen[p.ts]) { seen[p.ts] = 1; list.push(p.ts); }
              });
          });
          if (truncated) {
              // limite TB atteinte : liste incomplete -> repli statique
              // (on prefere des icones en trop que des icones masquees a tort)
              self._snapTsList = null;
              self._render();
              return;
          }
          list.sort(function(a,b){ return a - b; });
          self._snapTsList = list;
          self._render();
      })
      .catch(function(){
          if (self._probeRange !== rangeKey) return;
          self._probeRange = null; // invalide le cache -> retry au prochain onDataUpdated
          self._snapTsList = null; // repli : regle statique seule
          self._render();
      });
};

self.onDataUpdated = function() {
    var raw = self._collect();
    self._rows = self._pair(raw);
    self._probeSnapshots();
    self._render();
};"""

REPLACEMENTS = [('actionCell', OLD_ACTION, NEW_ACTION),
                ('onDataUpdated', OLD_UPDATE, NEW_UPDATE)]


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
    ap.add_argument('--dry-run', action='store_true',
                    help='Verifie les patterns OLD et affiche le delta, sans POST')
    args = ap.parse_args()
    t = login(args.user, args.pwd)
    w = http_get(f'/api/widgetType/{WIDGET_ID}', t)
    print(f'Widget: {w["name"]} ({w["fqn"]}) v{w.get("version","?")}')
    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Already patched (idempotent skip)')
        return
    new_cs = cs
    for name, old, new in REPLACEMENTS:
        n = new_cs.count(old)
        if n != 1:
            sys.exit(f'  [{name}] OLD pattern found {n} times (expected 1) -- widget code may have changed')
        new_cs = new_cs.replace(old, new, 1)
        print(f'  [{name}] OK (+{len(new)-len(old)} chars)')
    if args.dry_run:
        print(f'DRY-RUN: controllerScript {len(cs)} -> {len(new_cs)} chars. No POST.')
        return
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/backup/widgets-tduo-v1/events_history.before_nosnap.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'  Backup: {backup}')
    w['descriptor']['controllerScript'] = new_cs
    resp = http_post('/api/widgetType', w, t)
    print(f'Posted OK. New version: {resp.get("version","?")}')


if __name__ == '__main__':
    main()

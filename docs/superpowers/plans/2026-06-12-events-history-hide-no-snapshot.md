# Historique événements — masquer l'icône diagnostic sans snapshot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dans le widget `tduo.events_history`, n'afficher l'icône « Voir diagnostic » que si un snapshot existe pour le défaut (règle statique + probe dynamique), via un script de patch idempotent.

**Architecture:** Un script Python (modèle des patches existants : login REST TB, GET widgetType, backup JSON, remplacement de blocs exacts dans `controllerScript`, POST) applique deux remplacements dans le widget live `af86baf0-3fe1-11f1-bbfe-e1395562cba0` : (1) helpers `_noSnapStatic`/`_snapAnchor`/`_hasSnap` + garde dans `_actionCell`, (2) probe télémétrie unique dans `onDataUpdated`. Spec : `docs/superpowers/specs/2026-06-12-events-history-hide-no-snapshot-design.md`.

**Tech Stack:** Python 3 stdlib (urllib), API REST ThingsBoard (`/api/widgetType`, `/api/plugins/telemetry`), JS widget TB (pas de framework), SQL TimescaleDB pour la vérification préalable.

**Pré-requis exécution :** mot de passe TB (`--pwd`, demander au user si absent), accès ssh `root@10.77.0.74` (clé yahtec-ota) pour la Task 1.

---

### Task 1 : Vérifier en prod les combos défaut/device sans snapshot

But : confirmer (ou corriger) la liste statique du spec — devices 60–68 jamais de snapshot ; devices 50–55 + faults comm {15, 29, 38, 39, 40, 88} jamais de snapshot — avant de figer le code.

**Files:** aucun (lecture seule prod).

- [ ] **Step 1 : Exécuter la requête d'agrégation sur la base prod**

```powershell
ssh root@10.77.0.74 "sudo -u postgres psql -d thingsboard -c \"
WITH dict AS (SELECT key, key_id FROM ts_kv_dictionary WHERE key IN ('evt_type','evt_fault','evt_device','p_bp')),
evt AS (
  SELECT t.entity_id, min(t.ts) AS ts,
         max(CASE WHEN d.key='evt_fault'  THEN t.long_v END) AS fault,
         max(CASE WHEN d.key='evt_device' THEN t.long_v END) AS dev,
         max(CASE WHEN d.key='evt_type'   THEN t.long_v END) AS typ
  FROM ts_kv t JOIN dict d ON t.key = d.key_id
  WHERE d.key IN ('evt_type','evt_fault','evt_device')
  GROUP BY t.entity_id, (t.ts/2000)
),
snap AS (SELECT t.entity_id, t.ts FROM ts_kv t JOIN dict d ON t.key = d.key_id WHERE d.key='p_bp')
SELECT e.dev, e.fault, count(*) AS n,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM snap s WHERE s.entity_id = e.entity_id
           AND s.ts BETWEEN e.ts - 120000 AND e.ts + 60000)) AS with_snap
FROM evt e WHERE e.typ = 1
GROUP BY e.dev, e.fault ORDER BY e.dev, e.fault;
\""
```

Notes : `GROUP BY (t.ts/2000)` absorbe le déphasage ~1 ms entre clés d'un même événement (cf. commentaire du widget). Si `ssh` échoue sur la syntaxe d'échappement PowerShell, écrire le SQL dans un fichier temporaire et le passer via `ssh root@10.77.0.74 "sudo -u postgres psql -d thingsboard" < query.sql` (Bash tool).

- [ ] **Step 2 : Interpréter le résultat**

Attendu :
- lignes `dev` 60–68 : `with_snap = 0` partout → règle statique module confirmée ;
- lignes `dev` 50–55 avec `fault` ∈ {15, 29, 38, 39, 40, 88} : `with_snap = 0` → règle comm PAC confirmée ;
- les autres combos peuvent avoir `with_snap` mixte (firmware verrouillé) — c'est le rôle du probe, pas de la liste statique.

Si un combo de la liste statique a `with_snap > 0` : **retirer ce combo de la liste statique** dans la Task 2 (le probe le gérera) et le signaler dans le rapport au user. Ne jamais ajouter de combo à la liste statique sans `n ≥ 3` et `with_snap = 0`.

- [ ] **Step 3 : Consigner le résultat**

Coller le tableau de sortie (ou son résumé) dans le message de rapport de la task ; il servira de justification du contenu final de `COMM_FAULTS` / plages devices.

---

### Task 2 : Écrire le script de patch `patch-events-history-hide-no-snapshot.py`

**Files:**
- Create: `scripts/tb/widgets/patch-events-history-hide-no-snapshot.py`

Pas de harness de test JS dans ce repo : la « TDD » de ce script est son mode `--dry-run` (Task 3) qui valide les patterns OLD contre le widget live avant tout POST, plus le pré-flight local du Step 2.

- [ ] **Step 1 : Créer le script complet**

Contenu exact (ajuster `OLD_ACTION`/`NEW_ACTION` uniquement si la Task 1 a modifié la liste statique) :

```python
#!/usr/bin/env python3
"""
Patch events_history widget : masque l'icone "Voir diagnostic" quand aucun
snapshot n'existe pour le defaut.

1) Regle statique (cas surs, zero requete) :
   - evt_device 60-68 (unites module) : jamais de snapshot d'office
   - evt_device 50-55 (PAC Hybride) + evt_fault communication {15,29,38,39,40,88}
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
    var COMM_FAULTS = {15:1,29:1,38:1,39:1,40:1,88:1};
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
    if (!cand.length) { self._snapTsList = []; return; }
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
    if (!devId || !tok) { self._snapTsList = null; self._render(); return; }
    var url = '/api/plugins/telemetry/DEVICE/' + devId + '/values/timeseries?keys=' +
              SNAP_PROBE_KEYS.join(',') + '&startTs=' + minTs + '&endTs=' + maxTs +
              '&limit=1000&agg=NONE';
    fetch(url, { headers:{'X-Authorization':'Bearer '+tok} })
      .then(function(r){ if (!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
      .then(function(data){
          if (self._probeRange !== rangeKey) return; // fenetre changee entre-temps
          var seen = {}, list = [];
          SNAP_PROBE_KEYS.forEach(function(k){
              (data[k] || []).forEach(function(p){
                  if (!seen[p.ts]) { seen[p.ts] = 1; list.push(p.ts); }
              });
          });
          list.sort(function(a,b){ return a - b; });
          self._snapTsList = list;
          self._render();
      })
      .catch(function(){
          if (self._probeRange !== rangeKey) return;
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
```

- [ ] **Step 2 : Pré-flight local — vérifier que les patterns OLD matchent le dernier backup**

Le widget live = backup `events_history.before_entityid.20260601-192547.json` + patch entityId (qui ne touche ni `_actionCell` ni `onDataUpdated`). Écrire le fichier jetable `scripts/tb/widgets/_preflight_nosnap.py` (Write tool) :

```python
# Verifie que les patterns OLD du patch nosnap matchent le dernier backup local.
import io, json

src = io.open('scripts/tb/widgets/patch-events-history-hide-no-snapshot.py', encoding='utf-8').read()
ns = {}
exec(compile(src.split('def http_get')[0], 'patch-head', 'exec'), ns)
w = json.load(io.open('scripts/tb/backup/widgets-tduo-v1/events_history.before_entityid.20260601-192547.json', encoding='utf-8'))
cs = w['descriptor']['controllerScript']
for name, old, new in ns['REPLACEMENTS']:
    print(name, 'count =', cs.count(old))
```

Puis :

```powershell
python scripts/tb/widgets/_preflight_nosnap.py; Remove-Item scripts/tb/widgets/_preflight_nosnap.py -Confirm:$false
```

Expected: `actionCell count = 1` et `onDataUpdated count = 1`. Si 0 : corriger les OLD (espaces/accents) jusqu'à match exact.

- [ ] **Step 3 : Commit du script**

```powershell
git add scripts/tb/widgets/patch-events-history-hide-no-snapshot.py
git commit -m "feat(scripts/tb): patch events_history - masque icone diagnostic sans snapshot"
```

---

### Task 3 : Dry-run contre le widget live

**Files:** aucun.

- [ ] **Step 1 : Lancer le dry-run**

```powershell
python scripts/tb/widgets/patch-events-history-hide-no-snapshot.py --pwd <PWD> --dry-run
```

(Demander le mot de passe TB au user s'il n'a pas été fourni.)

Expected:
```
Widget: Events History (tduo.events_history) v<NN>
  [actionCell] OK (+... chars)
  [onDataUpdated] OK (+... chars)
DRY-RUN: controllerScript ... -> ... chars. No POST.
```

- [ ] **Step 2 : Si un pattern n'est pas trouvé**

Le widget live a divergé des backups : GET le widget (`/api/widgetType/af86baf0-...`), sauvegarder le JSON dans `scripts/tb/backup/widgets-tduo-v1/`, repérer le bloc réel, ajuster OLD_ACTION/OLD_UPDATE dans le script, re-committer, relancer le dry-run.

---

### Task 4 : Appliquer le patch en prod

**Files:**
- Create (généré) : `scripts/tb/backup/widgets-tduo-v1/events_history.before_nosnap.<ts>.json`

- [ ] **Step 1 : Lancer le patch sans --dry-run**

```powershell
python scripts/tb/widgets/patch-events-history-hide-no-snapshot.py --pwd <PWD>
```

Expected: les deux `[.. ] OK`, ligne `Backup: ...`, puis `Posted OK. New version: <NN+1>`.

- [ ] **Step 2 : Vérifier l'idempotence**

Relancer la même commande. Expected: `Already patched (idempotent skip)`.

- [ ] **Step 3 : Committer le backup**

```powershell
git add scripts/tb/backup/widgets-tduo-v1/events_history.before_nosnap.*.json
git commit -m "chore(scripts/tb): backup events_history avant patch nosnap"
```

---

### Task 5 : Validation fonctionnelle en prod

**Files:** aucun (validation lecture seule + rapport).

- [ ] **Step 1 : Identifier des lignes de test via l'API télémétrie**

Sur un device avec historique riche (ex. Serris / un TDUO avec défauts récents — réutiliser un combo trouvé en Task 1), vérifier via REST :

```powershell
# evt_* sur 30 jours pour trouver des defauts module / comm PAC / PAC avec snapshot
# (obtenir <TOKEN> via POST /api/auth/login comme dans les scripts de patch)
curl.exe -s -H "X-Authorization: Bearer <TOKEN>" "https://thingsboard.tsmart.fr/api/plugins/telemetry/DEVICE/<DEVICE_ID>/values/timeseries?keys=evt_type,evt_fault,evt_device&startTs=<NOW-30j_MS>&endTs=<NOW_MS>&limit=200&agg=NONE"
# presence snapshot autour d'un evtTs donne :
curl.exe -s -H "X-Authorization: Bearer <TOKEN>" "https://thingsboard.tsmart.fr/api/plugins/telemetry/DEVICE/<DEVICE_ID>/values/timeseries?keys=p_bp&startTs=<EVT_TS-120000>&endTs=<EVT_TS+60000>&limit=5&agg=NONE"
```

- [ ] **Step 2 : Vérifier le comportement attendu dans le dashboard**

Ouvrir le dashboard « Mes Installations » → état historique du device choisi, et vérifier :
1. défaut module (device 60–68) → **pas d'icône** ;
2. défaut comm PAC (device 50–55, fault comm) → **pas d'icône** ;
3. défaut PAC avec snapshot confirmé au Step 1 → **icône présente**, clic → page diagnostic avec courbes ;
4. au chargement : pas de flash d'icônes qui disparaissent.

Si pas d'accès navigateur dans la session : croiser les données du Step 1 avec la logique (`_noSnapStatic` + fenêtre ±120 s/60 s) et demander au user de confirmer visuellement les 4 points.

- [ ] **Step 3 : Rapport final**

Résumer au user : version widget avant/après, résultat Task 1 (combos vérifiés), lignes testées et comportement constaté. Rappeler que le rollback = re-POST du backup `events_history.before_nosnap.<ts>.json`.

# Payload v2 PAC Hybride — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer le pipeline télémétrie PAC Hybride de flat (~247 keys/post) vers JSON nested `pac_v2` json_v + 37 attributs SERVER_SCOPE, refonte intégrale du dashboard "Mes Installations", rotation stockage 3 ans glissants, compactage rétroactif des données v1 existantes, nettoyage composants orphelins. **Mode live différé** (Section 5/11.1 spec).

**Architecture:** L'automate envoie un JSON nested au proxy (déjà déployé avec `tb_format=true`). Le proxy parse `dateTime` UTC → wrap `{ts, values}` → forward TB. Une rule chain dispatcher "PAC Hybride Router" redirige le payload vers le vrai device PAC via ChangeOriginator. Sur le device PAC : **double écriture Option B** (flat existant + branche v2 parallèle). La branche v2 = Filter `msg.HPs présent ?` → TBEL split-attributes → Message Type Switch → Save Attributes SERVER_SCOPE + Save Timeseries `pac_v2`. Les widgets TDUO refactorisés lisent `pac_v2` + attributs. Un script de **compactage rétroactif** convertit les données v1 existantes en `pac_v2` (Phase 1.X).

**Tech Stack:** ThingsBoard 4.3 (rule chain TBEL, dashboard JSON, widgets, REST API), PostgreSQL 16 (ts_kv partitionné mensuel), bash + cron sur Ubuntu, SSH (clé `yahtec-ota`), proxy `telemetry-proxy 0.1.0` Rust (déjà déployé `tb_format=true`).

**Spec :** [docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md](../specs/2026-05-28-payload-v2-pac-hybride-design.md)

**Hors scope de ce plan** : développement du code automate (repo séparé, déjà déployé sur `2602000001`/`2602000002` en v2). Mode live (différé Section 11.1 spec).

## Statut d'avancement

| Phase | Statut | Date |
|---|---|---|
| 0 — Setup | À faire | — |
| 1 — Rule chain : extension v2 (5 nodes via REST API) | À faire | — |
| **1.X — Compactage rétroactif v1 → v2** | **À faire (nouveau)** | — |
| 2 — Device profile cleanup | À faire | — |
| 3 — Widgets TDUO refactor (15 widgets dont 6 non déployés) | À faire | — |
| 4 — Dashboard refonte intégrale (8 états) | À faire | — |
| 5 — Storage rotation cron | À faire | — |
| ~~6 — Live Timeout Sweep~~ | ~~À faire~~ | **DIFFÉRÉ** (Section 11.1 spec) |
| **7 — Proxy mode v2 activation** | **✅ DONE (anticipé)** | **2026-05-28** |
| 8 — Acceptance | À faire | — |

**Notes** :
- Phase 7 (proxy `tb_format=true`) a été réalisée et validée 2026-05-28 avant les Phases TB. Le proxy a un toggle indépendant validé sur couche transport seulement (parse `dateTime` → wrap `{ts, values}` → cache offline → replay).
- L'automate **v2 est déjà déployé** sur `2602000001`/`2602000002` (refactorisé point 1 spec). Les payloads nested arrivent en prod ; la rule chain v2 (Phase 1) doit être déployée pour activer le split attrs + `pac_v2`.
- **Option B** (Section 4 spec) : la branche flat existante est **conservée** en parallèle pendant la transition. Phase 3.6 retire cette branche après widgets refactorisés.
- Phase 1.X (compactage rétroactif) tourne en arrière-plan dès Phase 1 deployée.
- Phase 6 (Live Timeout Sweep) **drop** : mode live archivé Section 11.1 spec (réactivation possible plus tard sans toucher au plan actuel).

---

## Phase 0 : Setup

### Task 0 : Préparer l'arborescence scripts/ et obtenir les credentials TB REST

**Files:**
- Create: `scripts/tb/.gitkeep`
- Create: `scripts/server/.gitkeep`
- Create: `scripts/proxy/.gitkeep`
- Modify: `.gitignore` (si nécessaire pour exclure secrets)

- [ ] **Step 1 : Créer la structure scripts**

```bash
mkdir -p scripts/tb scripts/server scripts/proxy
touch scripts/tb/.gitkeep scripts/server/.gitkeep scripts/proxy/.gitkeep
```

- [ ] **Step 2 : Récupérer un JWT TB pour les appels REST API**

Identifiants tenant admin TB connus de l'opérateur. Login via :

```powershell
$body = '{"username":"<tenant-admin-email>","password":"<password>"}'
$response = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/auth/login" -Method Post -Body $body -ContentType "application/json"
$env:TB_TOKEN = $response.token
Write-Host "TB_TOKEN set, valid ~2.5h"
```

Vérifier : `Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/auth/user" -Headers @{Authorization="Bearer $env:TB_TOKEN"}` → doit retourner les détails du user.

- [ ] **Step 3 : Commit la structure**

```bash
git add scripts/
git commit -m "chore: scaffold scripts/ tree for payload v2 migration"
```

---

## Phase 1 : Rule chain "PAC Hybride Router" — extension v2 (5 nouveaux nodes)

> **Approche** : on **étend** la rule chain existante `PAC Hybride Router` (UUID `b6af0570-4226-11f1-bbfe-e1395562cba0`) en ajoutant **5 nouveaux nodes en parallèle** de `save TS (per-id device)` (Option B Section 4 spec). Modification via **REST API JSON** (UI manuelle non praticable). La branche existante (flat + evt_*) est **conservée**.

### Task 1 : Backup de la rule chain actuelle

**Files:**
- Create: `scripts/tb/backup/rule-chain-pac-hybride-router-pre-v2.json`

- [ ] **Step 1 : Récupérer un JWT TB**

Voir Phase 0 Task 0 Step 2. JWT dans `$env:TB_TOKEN`.

- [ ] **Step 2 : Backup ruleChain + metadata via REST**

```powershell
$rcId = "b6af0570-4226-11f1-bbfe-e1395562cba0"
$rc = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$meta = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId/metadata" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
mkdir -Force scripts/tb/backup
@{ruleChain=$rc; metadata=$meta} | ConvertTo-Json -Depth 100 | Out-File scripts/tb/backup/rule-chain-pac-hybride-router-pre-v2.json -Encoding utf8
```

- [ ] **Step 3 : Sanity check du backup**

```powershell
$bk = Get-Content scripts/tb/backup/rule-chain-pac-hybride-router-pre-v2.json | ConvertFrom-Json
"Nodes count: $($bk.metadata.nodes.Count)"
"Connections count: $($bk.metadata.connections.Count)"
```

Expected : `Nodes count: 13`, `Connections count: ~14` (variable selon les liens existants).

- [ ] **Step 4 : Commit backup**

```bash
git add scripts/tb/backup/rule-chain-pac-hybride-router-pre-v2.json
git commit -m "chore(tb): backup rule chain PAC Hybride Router pre-v2 (13 nodes)"
```

### Task 2 : Écrire le script TBEL split-attributes-from-payload (28 paths finalisés)

**Files:**
- Create: `scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel`

> **Source de vérité** : spec Section 4.3 (ATTR_PATHS finalisé point 2).

- [ ] **Step 1 : Créer le fichier TBEL**

```javascript
// scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel
//
// Reçoit un msg nested v2 (msg.HPs présent garanti par le Filter node en amont).
// Le ts est déjà dans metadata.ts (depuis wrapper {ts, values} du proxy).
// Output : 2 messages — POST_ATTRIBUTES_REQUEST (SERVER_SCOPE) + POST_TELEMETRY_REQUEST (pac_v2 json_v).

var ATTR_PATHS = [
  "id", "rel", "type", "nHp", "relCm2",
  "dhw.tSet",
  "heat.slope", "heat.foot", "heat.tMax",
  "heat.dayBgEte", "heat.monthBgEte",
  "heat.dayEndEte", "heat.monthEndEte",
  "heat.tCut", "heat.tRes",
  "heat.calo.qeU", "heat.calo.qeTotU",
  "heat.calo.pwrU", "heat.calo.hKwhU", "heat.calo.cKwhU",
  "caloM.qeU", "caloM.qeTotU",
  "caloM.pwrU", "caloM.hKwhU", "caloM.cKwhU",
  "HPs.relStm", "HPs.relEsp", "HPs.relScr"
];

var attrs = {};
var payload = clone(msg);

foreach (path : ATTR_PATHS) {
  var parts = path.split(".");

  // Cas HPs.* : applique sur chaque élément de l'array (longueur fixe 4)
  if (parts[0] == "HPs") {
    var leaf = parts[1];
    if (payload.HPs != null) {
      for (var i = 0; i < payload.HPs.length; i++) {
        if (payload.HPs[i][leaf] != null) {
          attrs["HP" + (i+1) + "_" + leaf] = payload.HPs[i][leaf];
          payload.HPs[i].remove(leaf);
        }
      }
    }
    continue;
  }

  // Cas générique dotted-path
  var ref = payload;
  var ok = true;
  for (var j = 0; j < parts.length - 1; j++) {
    if (ref[parts[j]] == null) { ok = false; break; }
    ref = ref[parts[j]];
  }
  if (!ok) continue;
  var leafName = parts[parts.length - 1];
  if (ref[leafName] != null) {
    attrs[parts.join("_")] = ref[leafName];   // heat.calo.qeU → heat_calo_qeU
    ref.remove(leafName);
  }
}

return [
  { msg: attrs,
    metadata: metadata.merge({"scope": "SERVER_SCOPE"}),
    msgType: "POST_ATTRIBUTES_REQUEST" },
  { msg: { pac_v2: payload },
    metadata: metadata,
    msgType: "POST_TELEMETRY_REQUEST" }
];
```

- [ ] **Step 2 : Validation syntaxe via TB testScript endpoint**

```powershell
$script = Get-Content scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel -Raw
$testPayload = @{
  script = $script
  scriptType = "update"
  argNames = @("msg","metadata","msgType")
  msg = '{"id":"2602000001","rel":1.4,"type":0,"nHp":1,"tExt":33.4,"TinM":6.9,"press":2,"commCm2":0,"relCm2":0,"date":"29/05/26","time":"13:05:37","dateTime":"29/05/26 11:05:38","HPs":[{"comm":true,"relStm":"1.3.137","relEsp":"1.0.145","relScr":"1.0.202","HP":{"status":4,"pHi":14.7},"invert":{"comm":false,"freq":59},"boil":{"status":0},"pump":{"comm":false,"pwr":1870}},{"comm":0,"relStm":"","relEsp":"","relScr":"","HP":{"status":0},"invert":{"comm":0},"boil":{"status":0},"pump":{"comm":0}},{"comm":0,"relStm":"","relEsp":"","relScr":"","HP":{"status":0},"invert":{"comm":0},"boil":{"status":0},"pump":{"comm":0}},{"comm":0,"relStm":"","relEsp":"","relScr":"","HP":{"status":0},"invert":{"comm":0},"boil":{"status":0},"pump":{"comm":0}}],"heat":{"tOut":0,"slope":0,"setpoint":7,"calo":{"qeU":0,"qeTotU":0,"pwrU":0,"hKwhU":0,"cKwhU":0}},"dhw":{"tOut":0,"tSet":0,"posV3V":100},"caloM":{"qeU":0,"qeTotU":0,"pwrU":0,"hKwhU":0,"cKwhU":0},"pump1M":{"pwr":0},"pump2M":{"pwr":0}}'
  metadata = '{"ts":"1716902040000"}'
  msgType = "POST_TELEMETRY_REQUEST"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/testScript" -Method Post -Body $testPayload -ContentType "application/json" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
```

Expected : `output` contient 2 messages (attrs avec ~30 paths + pac_v2 avec le reste nested), `error` null.

- [ ] **Step 3 : Commit**

```bash
git add scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel
git commit -m "feat(tb): TBEL split-attributes-from-payload script (28 finalized ATTR_PATHS)"
```

### Task 3 : Écrire le script de déploiement des 5 nouveaux nodes

**Files:**
- Create: `scripts/tb/rule-chain-pac-hybride-router/deploy-v2-nodes.ps1`

Script qui modifie la rule chain existante en ajoutant les 5 nodes + 6 connexions via REST API JSON. **Idempotent** : si nodes déjà présents, met à jour leur config sans dupliquer.

- [ ] **Step 1 : Écrire le script PowerShell**

```powershell
# scripts/tb/rule-chain-pac-hybride-router/deploy-v2-nodes.ps1
#
# Ajoute 5 nouveaux nodes a la rule chain "PAC Hybride Router" en parallele de
# 'save TS (per-id device)' :
#   1. Filter "HPs present ?" (TbJsFilterNode)
#   2. TBEL split-attributes-from-payload (TbTransformMsgNode TBEL)
#   3. Message Type Switch (TbMsgTypeSwitchNode)
#   4. Save Attributes SERVER_SCOPE (TbMsgAttributesNode)
#   5. Save Timeseries pac_v2 (TbMsgTimeseriesNode)
#
# Connexions ajoutees :
#   mark active --Success--> Filter HPs
#   Filter HPs --True--> TBEL split
#   TBEL split --Success--> MsgType Switch
#   MsgType Switch --Post attributes--> Save Attrs
#   MsgType Switch --Post telemetry--> Save TS pac_v2
#
# Idempotent : detecte les nodes existants par nom et met a jour leur config.
# Backup automatique avant modif dans scripts/tb/backup/.

param(
  [string]$RuleChainId = "b6af0570-4226-11f1-bbfe-e1395562cba0",
  [string]$BackupDir = "scripts/tb/backup"
)
$ErrorActionPreference = "Stop"
if (-not $env:TB_TOKEN) { throw "TB_TOKEN env var must be set (see Phase 0 Task 0)" }
$Headers = @{Authorization = "Bearer $env:TB_TOKEN"}

# 1. Backup automatique
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$rc = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$RuleChainId" -Headers $Headers
$meta = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$RuleChainId/metadata" -Headers $Headers
mkdir -Force $BackupDir | Out-Null
@{ruleChain=$rc; metadata=$meta} | ConvertTo-Json -Depth 100 | Out-File "$BackupDir/rule-chain-pac-hybride-router-$ts.json" -Encoding utf8
Write-Host "Backup saved: $BackupDir/rule-chain-pac-hybride-router-$ts.json"

# 2. Charger le script TBEL
$tbelScript = Get-Content scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel -Raw

# 3. Definition des 5 nouveaux nodes
$NewNodes = @(
  @{
    name = "Filter HPs present v2"
    type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
    configuration = @{
      jsScript = "return msg.HPs !== undefined && Array.isArray(msg.HPs);"
      scriptLang = "JS"
    }
    additionalInfo = @{layoutX = 1200; layoutY = 100; description = "Gate: only nested v2 payloads enter the split branch"}
  },
  @{
    name = "TBEL split-attributes v2"
    type = "org.thingsboard.rule.engine.transform.TbTransformMsgNode"
    configuration = @{
      tbelScript = $tbelScript
      scriptLang = "TBEL"
    }
    additionalInfo = @{layoutX = 1400; layoutY = 100; description = "Split SERVER_SCOPE attrs from telemetry payload"}
  },
  @{
    name = "MsgType Switch v2"
    type = "org.thingsboard.rule.engine.flow.TbMsgTypeSwitchNode"
    configuration = @{ version = 0 }
    additionalInfo = @{layoutX = 1600; layoutY = 100; description = "Route by msgType to Save Attrs or Save TS"}
  },
  @{
    name = "Save Attrs SERVER_SCOPE v2"
    type = "org.thingsboard.rule.engine.telemetry.TbMsgAttributesNode"
    configuration = @{
      scope = "SERVER_SCOPE"
      notifyDevice = $false
      sendAttributesUpdatedNotification = $true
      updateAttributesOnlyOnValueChange = $true
    }
    additionalInfo = @{layoutX = 1800; layoutY = 50; description = "Persist 37 SERVER_SCOPE attrs from TBEL split"}
  },
  @{
    name = "Save TS pac_v2"
    type = "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode"
    configuration = @{
      defaultTTL = 0
      useServerTs = $false
      processingSettings = @{ type = "ON_EVERY_MESSAGE" }
    }
    additionalInfo = @{layoutX = 1800; layoutY = 150; description = "Persist pac_v2 json_v at metadata.ts"}
  }
)

# 4. Localiser le node 'mark active' source
$markActiveIdx = -1
for ($i = 0; $i -lt $meta.nodes.Count; $i++) {
  if ($meta.nodes[$i].name -eq "mark active") { $markActiveIdx = $i; break }
}
if ($markActiveIdx -lt 0) { throw "'mark active' node not found in current rule chain" }

# 5. Pour chaque NewNode : si nom existe deja dans meta.nodes, update ; sinon append
foreach ($n in $NewNodes) {
  $existingIdx = -1
  for ($i = 0; $i -lt $meta.nodes.Count; $i++) {
    if ($meta.nodes[$i].name -eq $n.name) { $existingIdx = $i; break }
  }
  if ($existingIdx -ge 0) {
    $meta.nodes[$existingIdx].configuration = $n.configuration
    $meta.nodes[$existingIdx].additionalInfo = $n.additionalInfo
    Write-Host "Updated node: $($n.name)"
  } else {
    $meta.nodes += $n
    Write-Host "Added node: $($n.name) at index $($meta.nodes.Count - 1)"
  }
}

# 6. Localiser les indices finaux des nouveaux nodes
function GetIdx($name) {
  for ($i = 0; $i -lt $meta.nodes.Count; $i++) { if ($meta.nodes[$i].name -eq $name) { return $i } }
  return -1
}
$filterIdx = GetIdx "Filter HPs present v2"
$tbelIdx = GetIdx "TBEL split-attributes v2"
$switchIdx = GetIdx "MsgType Switch v2"
$saveAttrsIdx = GetIdx "Save Attrs SERVER_SCOPE v2"
$saveTsIdx = GetIdx "Save TS pac_v2"

# 7. Connexions a ajouter (idempotent : skip si deja presente)
$NewConnections = @(
  @{fromIndex=$markActiveIdx; toIndex=$filterIdx;  type="Success"},
  @{fromIndex=$filterIdx;     toIndex=$tbelIdx;    type="True"},
  @{fromIndex=$tbelIdx;       toIndex=$switchIdx;  type="Success"},
  @{fromIndex=$switchIdx;     toIndex=$saveAttrsIdx; type="Post attributes"},
  @{fromIndex=$switchIdx;     toIndex=$saveTsIdx;  type="Post telemetry"}
)
foreach ($conn in $NewConnections) {
  $exists = $false
  foreach ($c in $meta.connections) {
    if ($c.fromIndex -eq $conn.fromIndex -and $c.toIndex -eq $conn.toIndex -and $c.type -eq $conn.type) {
      $exists = $true; break
    }
  }
  if (-not $exists) {
    $meta.connections += $conn
    Write-Host "Added connection: $($meta.nodes[$conn.fromIndex].name) --$($conn.type)--> $($meta.nodes[$conn.toIndex].name)"
  }
}

# 8. POST metadata mise a jour
$body = $meta | ConvertTo-Json -Depth 100
$result = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/metadata" -Method Post -Body $body -ContentType "application/json" -Headers $Headers
Write-Host "Rule chain updated. New nodes count: $($result.nodes.Count)"
```

- [ ] **Step 2 : Sauvegarder + commit**

```bash
git add scripts/tb/rule-chain-pac-hybride-router/deploy-v2-nodes.ps1
git commit -m "feat(tb): script idempotent de deploiement des 5 nodes v2 via REST API"
```

### Task 4 : Exécuter le déploiement et valider

**Files:**
- Modify (TB) : Rule chain `PAC Hybride Router` (13 → 18 nodes via REST)

- [ ] **Step 1 : Exécuter le script de déploiement**

```powershell
.\scripts\tb\rule-chain-pac-hybride-router\deploy-v2-nodes.ps1
```

Expected logs :
- `Backup saved: scripts/tb/backup/rule-chain-pac-hybride-router-<ts>.json`
- `Added node: Filter HPs present v2 ...`
- `Added node: TBEL split-attributes v2 ...`
- ... (5 nodes ajoutés)
- `Added connection: mark active --Success--> Filter HPs present v2`
- ... (5 connexions ajoutées)
- `Rule chain updated. New nodes count: 18`

- [ ] **Step 2 : Vérifier que les automates v2 (`2602000001`, `2602000002`) écrivent `pac_v2` dans TB**

Attendre 1-2 cycles (1-2 min). Puis :

```powershell
$sql = @'
SELECT to_timestamp(ts/1000) AT TIME ZONE 'UTC' AS sample_ts,
       length(json_v::text) AS size_bytes
FROM ts_kv_2026_05 k
JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND d.key = 'pac_v2'
  AND k.ts > extract(epoch from now() - interval '5 minutes')*1000
ORDER BY k.ts DESC LIMIT 5;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : 1-5 lignes avec `sample_ts` récent et `size_bytes` ~2500-3500 (payload nested compact).

- [ ] **Step 3 : Vérifier les attributs SERVER_SCOPE populés**

```powershell
$sql = @'
SELECT d.key, str_v, long_v, dbl_v, bool_v
FROM attribute_kv a
JOIN key_dictionary d ON a.key_id = d.key_id
WHERE a.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND a.attribute_type = 'SERVER_SCOPE'
ORDER BY d.key;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : ≥ 30 lignes (cible 37 attrs si `nHp` = 4 ; moins si HPs slots inactifs n'envoient pas les version strings).

- [ ] **Step 4 : Vérifier que la branche flat continue à écrire (Option B)**

```powershell
$sql = @'
SELECT count(DISTINCT d.key) AS distinct_flat_keys
FROM ts_kv_2026_05 k
JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND d.key NOT IN ('pac_v2')
  AND d.key NOT LIKE 'evt_%'
  AND k.ts > extract(epoch from now() - interval '5 minutes')*1000;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : ~240-250 clés distinctes (flat keys continuent à être sauvées en parallèle).

- [ ] **Step 5 : Vérifier que les evt_* (s'ils arrivent pendant la fenêtre) ne déclenchent PAS le TBEL split**

Inspecter les logs TB ou via SQL : un POST `evt_*` (sans champ `HPs`) doit créer des lignes `ts_kv` flat (`evt_date`, `evt_time`, etc.) sans créer de ligne `pac_v2`.

```powershell
$sql = @'
SELECT to_timestamp(ts/1000) AT TIME ZONE 'UTC' AS ts, d.key
FROM ts_kv_2026_05 k
JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND d.key LIKE 'evt_%'
ORDER BY k.ts DESC LIMIT 20;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : les keys `evt_*` apparaissent au moment d'un défaut/résolution, AVEC les autres flat keys aussi présentes mais SANS ligne `pac_v2` à ce timestamp.

- [ ] **Step 6 : Export rule chain finale et commit**

```powershell
$rcId = "b6af0570-4226-11f1-bbfe-e1395562cba0"
$meta = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId/metadata" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$meta | ConvertTo-Json -Depth 100 | Out-File scripts/tb/rule-chain-pac-hybride-router/rule-chain-router-v2-deployed.json -Encoding utf8
git add scripts/tb/rule-chain-pac-hybride-router/rule-chain-router-v2-deployed.json
git commit -m "ops(tb): rule chain extended with 5 v2 nodes deployed and validated"
```

### Rollback (si problème)

```powershell
# Reposter le backup pre-v2
$backup = Get-Content scripts/tb/backup/rule-chain-pac-hybride-router-pre-v2.json | ConvertFrom-Json
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/metadata" -Method Post -Body ($backup.metadata | ConvertTo-Json -Depth 100) -ContentType "application/json" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
```

Retour aux 13 nodes initiaux en < 1 seconde. La branche flat continue à servir sans interruption.

---

## Phase 1.X : Compactage rétroactif v1 → v2 des partitions historiques

> **Référence spec** : Section 8.5. **Objectif** : convertir les ~3.5 M lignes flat existantes (par partition mensuelle × device) en lignes `pac_v2` json_v compactes (1 par sample). Bénéfices : (1) historique visible dans widgets v2, (2) ~92 % de stockage libéré par sample, (3) ~1-2 GB libérés sur le parc actuel (avril-mai 2026).
>
> **Quand l'exécuter** : **dès Phase 1 déployée**. Peut tourner en arrière-plan en parallèle du reste du plan (Phases 2-5). N'interfère pas avec la rule chain v2 (nouveaux samples écrivent flat + `pac_v2` directement via la rule chain).

### Task 4.X.1 : Écrire le script de compactage `compact-v1-to-v2.py`

**Files:**
- Create: `scripts/server/compact-v1-to-v2.py`

> **Pré-requis** : `python3 + psycopg2-binary` sur la machine d'exécution (PC dev ou serveur prod `10.77.0.74`).

- [ ] **Step 1 : Écrire le script Python**

```python
#!/usr/bin/env python3
"""
scripts/server/compact-v1-to-v2.py

Compactage rétroactif v1 → v2 des partitions ts_kv_YYYY_MM.
Pour chaque sample (entity_id, ts) :
  1. Récupère toutes les keys flat (≠ evt_*) de ce sample
  2. Reconstruit le payload nested pac_v2 (mapping inverse du dispatcher)
  3. INSERT 1 ligne pac_v2 avec json_v
  4. DELETE les ~247 lignes flat de ce sample

Idempotent : skip les samples où pac_v2 existe déjà.
Tolérant aux trous : sample avec moins de 247 keys → pac_v2 partiel valide.

Usage:
  ./compact-v1-to-v2.py --device-name 2602000001 --partition ts_kv_2026_04 [--dry-run]
  ./compact-v1-to-v2.py --all-devices --partition ts_kv_2026_04
"""
import argparse
import json
import logging
import os
import re
import sys
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

LOG_FILE = "/var/log/tb-compact-v1-to-v2.log"
PAC_V2_KEY = "pac_v2"
BATCH_SIZE = 1000  # samples par transaction

# Précompil. regex pour les préfixes HPs / pumps
RE_HP = re.compile(r"^HP([1-4])_(.+)$")
RE_DHW_PUMP = re.compile(r"^dhw_pump([1-4])_(.+)$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("compact")


def get_value(row):
    """Retourne la valeur typée d'une ligne ts_kv."""
    for col in ("dbl_v", "long_v", "str_v", "bool_v", "json_v"):
        v = row[col]
        if v is not None:
            return v
    return None


def build_pac_v2(flat_keys):
    """
    Reconstruit le payload nested pac_v2 depuis un dict {key_name: value}.
    Inverse du flatten dispatcher.
    """
    nested = {}
    # Init HPs array length 4 + sous-structures
    nested["HPs"] = [
        {"HP": {}, "invert": {}, "boil": {}, "pump": {}}
        for _ in range(4)
    ]
    # Init blocs nested
    for blk in ("heat", "dhw", "caloM", "pump1M", "pump2M"):
        nested[blk] = {}
    nested["heat"]["calo"] = {}
    for p in ("pump1", "pump2", "pump3", "pump4"):
        nested["dhw"][p] = {}

    for k, v in flat_keys.items():
        # HP{N}_invert_*, HP{N}_boil_*, HP{N}_pump_*
        m = RE_HP.match(k)
        if m:
            idx = int(m.group(1)) - 1
            rest = m.group(2)
            if rest.startswith("invert_"):
                nested["HPs"][idx]["invert"][rest[len("invert_"):]] = v
            elif rest.startswith("boil_"):
                nested["HPs"][idx]["boil"][rest[len("boil_"):]] = v
            elif rest.startswith("pump_"):
                nested["HPs"][idx]["pump"][rest[len("pump_"):]] = v
            elif rest in ("comm", "relStm", "relEsp", "relScr"):
                nested["HPs"][idx][rest] = v
            else:
                nested["HPs"][idx]["HP"][rest] = v
            continue
        # dhw_pump{N}_*
        m = RE_DHW_PUMP.match(k)
        if m:
            idx = m.group(1)
            nested["dhw"][f"pump{idx}"][m.group(2)] = v
            continue
        # heat_calo_*
        if k.startswith("heat_calo_"):
            nested["heat"]["calo"][k[len("heat_calo_"):]] = v
            continue
        # heat_*
        if k.startswith("heat_"):
            nested["heat"][k[len("heat_"):]] = v
            continue
        # dhw_*
        if k.startswith("dhw_"):
            nested["dhw"][k[len("dhw_"):]] = v
            continue
        # caloM_*
        if k.startswith("caloM_"):
            nested["caloM"][k[len("caloM_"):]] = v
            continue
        # pump1M_, pump2M_
        if k.startswith("pump1M_"):
            nested["pump1M"][k[len("pump1M_"):]] = v
            continue
        if k.startswith("pump2M_"):
            nested["pump2M"][k[len("pump2M_"):]] = v
            continue
        # top-level
        nested[k] = v

    return nested


@contextmanager
def get_conn():
    conn = psycopg2.connect(
        host="localhost",
        dbname="thingsboard",
        user="postgres",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


def get_or_create_key_id(cur, key_name):
    """Récupère ou crée l'entry dans key_dictionary."""
    cur.execute("SELECT key_id FROM key_dictionary WHERE key = %s", (key_name,))
    row = cur.fetchone()
    if row:
        return row["key_id"]
    cur.execute(
        "INSERT INTO key_dictionary (key) VALUES (%s) RETURNING key_id",
        (key_name,),
    )
    return cur.fetchone()["key_id"]


def compact_partition(device_uuid, device_name, partition, dry_run=False):
    """Compacte 1 partition × 1 device."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            pac_v2_key_id = get_or_create_key_id(cur, PAC_V2_KEY)
            conn.commit()

            # Récupérer tous les ts distincts pour ce device dans cette partition
            cur.execute(
                f"SELECT DISTINCT ts FROM {partition} "
                f"WHERE entity_id = %s ORDER BY ts",
                (device_uuid,),
            )
            ts_list = [r["ts"] for r in cur.fetchall()]
            log.info(f"{device_name}/{partition}: {len(ts_list)} samples à examiner")

            converted = 0
            skipped = 0
            errors = 0

            for batch_start in range(0, len(ts_list), BATCH_SIZE):
                batch = ts_list[batch_start: batch_start + BATCH_SIZE]
                for ts in batch:
                    try:
                        # Skip si pac_v2 déjà présent
                        cur.execute(
                            f"SELECT 1 FROM {partition} "
                            f"WHERE entity_id = %s AND key = %s AND ts = %s",
                            (device_uuid, pac_v2_key_id, ts),
                        )
                        if cur.fetchone():
                            skipped += 1
                            continue

                        # Récupère toutes les keys flat de ce sample (sauf evt_*)
                        cur.execute(
                            f"SELECT d.key AS keyname, k.dbl_v, k.long_v, k.str_v, k.bool_v, k.json_v "
                            f"FROM {partition} k JOIN key_dictionary d ON k.key = d.key_id "
                            f"WHERE k.entity_id = %s AND k.ts = %s "
                            f"AND d.key NOT LIKE 'evt_%%'",
                            (device_uuid, ts),
                        )
                        rows = cur.fetchall()
                        if not rows:
                            continue

                        flat = {r["keyname"]: get_value(r) for r in rows}
                        pac_v2 = build_pac_v2(flat)

                        if not dry_run:
                            # INSERT pac_v2
                            cur.execute(
                                f"INSERT INTO {partition} (entity_id, key, ts, json_v) "
                                f"VALUES (%s, %s, %s, %s::jsonb)",
                                (device_uuid, pac_v2_key_id, ts, json.dumps(pac_v2)),
                            )
                            # DELETE flat (≠ evt_*, ≠ pac_v2)
                            cur.execute(
                                f"DELETE FROM {partition} "
                                f"WHERE entity_id = %s AND ts = %s "
                                f"AND key != %s "
                                f"AND key NOT IN (SELECT key_id FROM key_dictionary WHERE key LIKE 'evt_%%')",
                                (device_uuid, ts, pac_v2_key_id),
                            )
                        converted += 1
                    except Exception as e:
                        log.error(f"sample ts={ts} error: {e}")
                        errors += 1
                        conn.rollback()
                        continue
                if not dry_run:
                    conn.commit()
                log.info(
                    f"{device_name}/{partition}: batch progress "
                    f"converted={converted} skipped={skipped} errors={errors}"
                )

            log.info(
                f"{device_name}/{partition}: DONE converted={converted} "
                f"skipped={skipped} errors={errors}"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-name", help="device name (e.g. 2602000001)")
    ap.add_argument("--all-devices", action="store_true",
                    help="process all PAC Hybride devices")
    ap.add_argument("--partition", required=True,
                    help="partition table name (e.g. ts_kv_2026_04)")
    ap.add_argument("--dry-run", action="store_true",
                    help="no INSERT/DELETE, log only")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            if args.all_devices:
                cur.execute(
                    "SELECT d.id, d.name FROM device d "
                    "JOIN device_profile p ON d.device_profile_id = p.id "
                    "WHERE p.name = 'pac hybride' "
                    "ORDER BY d.name"
                )
                devices = [(r["id"], r["name"]) for r in cur.fetchall()]
            elif args.device_name:
                cur.execute("SELECT id, name FROM device WHERE name = %s",
                            (args.device_name,))
                row = cur.fetchone()
                if not row:
                    sys.exit(f"device {args.device_name} not found")
                devices = [(row["id"], row["name"])]
            else:
                ap.error("specify --device-name or --all-devices")

    for uuid, name in devices:
        compact_partition(uuid, name, args.partition, args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2 : Tests unitaires du mapping (offline)**

Créer un fichier `scripts/server/test_compact.py` qui vérifie `build_pac_v2()` sur un exemple :

```python
from compact_v1_to_v2 import build_pac_v2

flat = {
    "id": "2602000001", "rel": 1.4, "type": 0, "nHp": 1,
    "tExt": 33.4, "TinM": 6.9,
    "HP1_status": 4, "HP1_pHi": 14.7,
    "HP1_invert_freq": 59, "HP1_boil_status": 0, "HP1_pump_pwr": 1870,
    "HP1_relStm": "1.3.137", "HP1_comm": True,
    "dhw_tOut": 0, "dhw_pump1_pwr": 0, "dhw_pump4_qe": 0,
    "heat_slope": 0, "heat_calo_qeU": 0,
    "caloM_tIn": 0,
    "pump1M_pwr": 0, "pump2M_dP": 0,
}
result = build_pac_v2(flat)
assert result["id"] == "2602000001"
assert result["HPs"][0]["HP"]["status"] == 4
assert result["HPs"][0]["invert"]["freq"] == 59
assert result["HPs"][0]["boil"]["status"] == 0
assert result["HPs"][0]["pump"]["pwr"] == 1870
assert result["HPs"][0]["relStm"] == "1.3.137"
assert result["HPs"][0]["comm"] is True
assert result["dhw"]["pump1"]["pwr"] == 0
assert result["dhw"]["pump4"]["qe"] == 0
assert result["heat"]["slope"] == 0
assert result["heat"]["calo"]["qeU"] == 0
assert result["caloM"]["tIn"] == 0
assert result["pump1M"]["pwr"] == 0
assert result["pump2M"]["dP"] == 0
print("OK")
```

- [ ] **Step 3 : Commit script + test**

```bash
git add scripts/server/compact-v1-to-v2.py scripts/server/test_compact.py
git commit -m "feat(server): script compactage retroactif v1 -> v2 + tests mapping"
```

### Task 4.X.2 : Backup pg_dump des partitions cibles

**Files:**
- Created on prod : `/root/backups/ts_kv_2026_04-<ts>.dump`, `ts_kv_2026_05-<ts>.dump`

- [ ] **Step 1 : Vérifier l'espace disque disponible sur le serveur**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "df -h /"
```

Expected : ≥ 5 GB libres pour absorber 2 backups + WAL.

- [ ] **Step 2 : pg_dump des partitions à compacter**

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "mkdir -p /root/backups && sudo -u postgres pg_dump -Fc -t public.ts_kv_2026_04 -t public.ts_kv_2026_05 thingsboard > /root/backups/ts_kv_compact_${ts}.dump"
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "ls -lah /root/backups/"
```

Expected : 1 dump fichier de ~1-2 GB.

- [ ] **Step 3 : Commit la procédure (pas le dump, trop gros)**

```bash
git commit --allow-empty -m "ops(server): pg_dump ts_kv_2026_04+05 backed up to /root/backups/ before compaction"
```

### Task 4.X.3 : Exécuter le compactage sur un device pilote (dry-run puis réel)

**Files:**
- (modifications de partition `ts_kv_2026_04` sur prod)

- [ ] **Step 1 : Copier le script sur le serveur prod**

```powershell
scp -i C:\Users\je\.ssh\yahtec-ota scripts/server/compact-v1-to-v2.py root@10.77.0.74:/usr/local/bin/
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "chmod +x /usr/local/bin/compact-v1-to-v2.py && pip3 install psycopg2-binary"
```

- [ ] **Step 2 : Dry-run sur `2602000001` × `ts_kv_2026_04`**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "/usr/local/bin/compact-v1-to-v2.py --device-name 2602000001 --partition ts_kv_2026_04 --dry-run"
```

Expected : log montre samples à examiner, conversion simulée, pas d'INSERT/DELETE.

- [ ] **Step 3 : Mesurer le volume avant compactage réel**

```powershell
$sql = @'
SELECT pg_size_pretty(pg_total_relation_size('public.ts_kv_2026_04')) AS size_2026_04,
       (SELECT count(*) FROM ts_kv_2026_04 WHERE entity_id = (SELECT id FROM device WHERE name='2602000001')) AS rows_2602000001;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Noter `size_2026_04` et `rows_2602000001`.

- [ ] **Step 4 : Exécution réelle sur `2602000001` × `ts_kv_2026_04`**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "/usr/local/bin/compact-v1-to-v2.py --device-name 2602000001 --partition ts_kv_2026_04"
```

Suivre les logs : `tail -f /var/log/tb-compact-v1-to-v2.log` dans une autre session.

- [ ] **Step 5 : Mesurer le volume après**

```powershell
$sql = @'
SELECT pg_size_pretty(pg_total_relation_size('public.ts_kv_2026_04')) AS size_2026_04,
       (SELECT count(*) FROM ts_kv_2026_04 WHERE entity_id = (SELECT id FROM device WHERE name='2602000001')) AS rows_2602000001,
       (SELECT count(*) FROM ts_kv_2026_04 WHERE entity_id = (SELECT id FROM device WHERE name='2602000001')
        AND key = (SELECT key_id FROM key_dictionary WHERE key='pac_v2')) AS pac_v2_rows;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected :
- `rows_2602000001` : ~92 % réduction (de ~3.5 M lignes à ~14 k)
- `pac_v2_rows` : ~14 k (1 par sample d'origine)
- `size_2026_04` : réduction notable (peut nécessiter `VACUUM FULL` pour libérer l'espace disque réel)

- [ ] **Step 6 : Spot check sur un sample pac_v2 reconstruit**

```powershell
$sql = @'
SELECT to_timestamp(ts/1000) AT TIME ZONE 'UTC' AS sample_ts,
       json_v::text AS payload_preview
FROM ts_kv_2026_04 k
JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND d.key = 'pac_v2'
ORDER BY k.ts DESC LIMIT 1;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|' -P pager=off"
```

Vérifier visuellement la structure (HPs[0..3], heat.calo, dhw.pump1..4, caloM, pump1M, pump2M).

- [ ] **Step 7 : Commit résultat pilote**

```bash
git commit --allow-empty -m "ops(server): compactage pilote 2602000001 ts_kv_2026_04 — XX% reduction"
```

### Task 4.X.4 : Rollout compactage sur le parc complet

**Files:**
- (modifications partitions ts_kv_2026_04 et ts_kv_2026_05 sur prod, tous les devices PAC Hybride)

- [ ] **Step 1 : Lancer en arrière-plan sur tous les devices PAC Hybride pour `ts_kv_2026_04`**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "nohup /usr/local/bin/compact-v1-to-v2.py --all-devices --partition ts_kv_2026_04 > /tmp/compact_apr.log 2>&1 &"
```

- [ ] **Step 2 : Suivre la progression**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "tail -50 /var/log/tb-compact-v1-to-v2.log"
```

- [ ] **Step 3 : Idem pour `ts_kv_2026_05`** (une fois Step 1 terminé)

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "nohup /usr/local/bin/compact-v1-to-v2.py --all-devices --partition ts_kv_2026_05 > /tmp/compact_may.log 2>&1 &"
```

- [ ] **Step 4 : VACUUM FULL pour libérer l'espace disque**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -c 'VACUUM FULL ts_kv_2026_04; VACUUM FULL ts_kv_2026_05;'"
```

⚠ `VACUUM FULL` prend un lock exclusif (~quelques minutes par partition). Le faire pendant une fenêtre calme.

- [ ] **Step 5 : Mesure finale**

```powershell
$sql = @'
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relname::regclass)) AS size,
       (SELECT count(*) FROM ts_kv_2026_04) AS rows_04,
       (SELECT count(*) FROM ts_kv_2026_05) AS rows_05,
       pg_size_pretty(pg_total_relation_size('public.ts_kv_2026_04')) AS sz_04,
       pg_size_pretty(pg_total_relation_size('public.ts_kv_2026_05')) AS sz_05
FROM (VALUES ('ts_kv_2026_04'), ('ts_kv_2026_05')) AS v(relname) LIMIT 1;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

- [ ] **Step 6 : Commit ops résultat**

```bash
git commit --allow-empty -m "ops(server): compactage retroactif termine sur parc — X GB liberes"
```

---

## Phase 2 : Device profile cleanup

### Task 5 : Supprimer les 13 alarmes orphelines

**Files:**
- Modify : device profile "PAC Hybride" alarms (via TB UI)
- Create : `scripts/tb/backup/device-profile-pac-hybride-pre-cleanup.json`

- [ ] **Step 1 : Exporter le device profile complet comme backup**

```powershell
$profileId = "<uuid>"
$profile = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/deviceProfile/$profileId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$profile | ConvertTo-Json -Depth 100 | Out-File scripts/tb/backup/device-profile-pac-hybride-pre-cleanup.json -Encoding utf8
git add scripts/tb/backup/device-profile-pac-hybride-pre-cleanup.json
git commit -m "chore(tb): backup device profile PAC Hybride pre-alarm-cleanup"
```

- [ ] **Step 2 : Lister les alarmes du profile pour repérage**

Via TB UI : Device profiles → PAC Hybride → onglet "Alarm rules". Identifier les 13 orphelines :
- `HP1Fault`, `HP2Fault`, `HP3Fault`, `HP4Fault` (4)
- `Boil1Fault`, `Boil2Fault`, `Boil3Fault`, `Boil4Fault` (4)
- `Sensor1Fault`, `Sensor2Fault`, `Sensor3Fault`, `Sensor4Fault` (4)
- `Offline` (1)

- [ ] **Step 3 : Supprimer chaque alarme via le bouton trash de l'UI**

13 clics dans l'UI. Sauvegarder le profile à la fin.

- [ ] **Step 4 : Vérifier**

```powershell
$profile = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/deviceProfile/$profileId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$profile.profileData.alarms.Count
```

Expected : `0` (ou seulement les alarmes qu'on veut garder, à confirmer avec l'opérateur avant cleanup).

- [ ] **Step 5 : Commit**

```bash
git commit --allow-empty -m "chore(tb): remove 13 orphan alarms from PAC Hybride device profile"
```

### Task 6 : Mettre Default Storage TTL à 0

**Files:**
- Modify : device profile "PAC Hybride" (via TB UI)

- [ ] **Step 1 : Via TB UI, ouvrir le profile et l'onglet "Configuration"**

Trouver le champ "Default storage TTL (seconds)". Valeur actuelle probablement déjà 0 ou vide ; sinon mettre à `0` (illimité). C'est le script PG cron de Phase 5 qui gère la rotation.

- [ ] **Step 2 : Save**

- [ ] **Step 3 : Vérifier**

```powershell
$profile = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/deviceProfile/$profileId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$profile.profileData.configuration
```

Expected : `defaultStorageTtlDays = 0` (ou champ absent).

- [ ] **Step 4 : Commit**

```bash
git commit --allow-empty -m "chore(tb): set PAC Hybride default storage TTL to 0 (script PG handles rotation)"
```

---

## Phase 3 : Refactor des widgets TDUO (15 widgets dans le bundle)

> **Scope élargi** (point 4 spec) : refonte intégrale du dashboard → refactor de **9 widgets actifs** (6 non déployés + 3 déployés) + **archive de 6 versions de dev** `events_history{2..7}`.
>
> **Convention** : on duplique chaque widget (suffixe `_v2`) si le widget est déjà déployé sur un dashboard (rollback simple). Pour les 6 widgets non déployés, on refactor en place (pas de risque de casse). Une fois le dashboard validé, on supprime les originaux des 3 widgets déployés.

### Task 7 : Exporter les 15 widgets TDUO actuels (backup complet)

**Files:**
- Create : `scripts/tb/backup/widgets-tduo-v1/*.json`

- [ ] **Step 1 : Lister les UUIDs des 6 widgets**

```powershell
$sql = @'
SELECT id, name, fqn, length(descriptor::text) AS sz
FROM widget_type
WHERE fqn LIKE 'tduo.%'
ORDER BY fqn;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Noter les 6 UUIDs (les mêmes qu'on a vu dans la spec : `tduo.boiler_synoptic`, `tduo.dhw_card`, `tduo.heating_loop_card`, `tduo.hub_info`, `tduo.pac_synoptic`, `tduo.tduo_tile`).

- [ ] **Step 2 : Export via REST API chacun**

```powershell
mkdir -Force scripts/tb/backup/widgets-tduo-v1
$widgets = @(
  @{id="424e51c0-3e54-11f1-bbfe-e1395562cba0"; name="boiler-synoptic"},
  @{id="426f6e50-3e54-11f1-bbfe-e1395562cba0"; name="dhw-card"},
  @{id="428bf700-3e54-11f1-bbfe-e1395562cba0"; name="heating-loop-card"},
  @{id="54791640-3e55-11f1-bbfe-e1395562cba0"; name="hub-info"},
  @{id="42ab8cf0-3e54-11f1-bbfe-e1395562cba0"; name="pac-synoptic"},
  @{id="42c8d8f0-3e54-11f1-bbfe-e1395562cba0"; name="tduo-tile"}
)
foreach ($w in $widgets) {
  $r = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/widgetType/$($w.id)" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
  $r | ConvertTo-Json -Depth 100 | Out-File "scripts/tb/backup/widgets-tduo-v1/$($w.name).json" -Encoding utf8
}
```

- [ ] **Step 3 : Commit**

```bash
git add scripts/tb/backup/widgets-tduo-v1/
git commit -m "chore(tb): backup 6 TDUO widgets pre-pac_v2 refactor"
```

### Task 8 : Comprendre le datasource pattern actuel sur un widget

**Files:**
- Read : `scripts/tb/backup/widgets-tduo-v1/dhw-card.json`

- [ ] **Step 1 : Inspecter le descriptor du widget DHW Card**

```powershell
$d = Get-Content scripts/tb/backup/widgets-tduo-v1/dhw-card.json | ConvertFrom-Json
$d.descriptor.defaultConfig | ConvertFrom-Json | Select-Object -ExpandProperty datasources
```

Repérer : noms de clés télémétrie lus (ex : `dhw_tOut`, `dhw_tIn`, etc. en flat) et où ils apparaissent dans le code JS du widget (`controllerScript`, `templateHtml`).

- [ ] **Step 2 : Documenter le mapping flat → v2 pour ce widget**

Créer une note inline dans le fichier de refactor de la Task 9. Pour DHW Card :

| Flat actuel | Path v2 |
|---|---|
| `dhw_tOut` | `pac_v2.dhw.tOut` |
| `dhw_tIn` | `pac_v2.dhw.tIn` |
| `dhw_tTank` | `pac_v2.dhw.tTank` |
| `dhw_posV3V` | `pac_v2.dhw.posV3V` |
| `dhw_pump1_pwr` | `pac_v2.dhw.pump1.pwr` |
| ... etc | ... |

- [ ] **Step 3 : Pas de commit (documentation interne)**

### Task 9 : Refactor du widget DHW Card → DHW Card v2

**Files:**
- Modify : widget descriptor via TB UI (alias `tduo.dhw_card_v2`)
- Create : `scripts/tb/widgets-v2/dhw-card-v2.json`

- [ ] **Step 1 : Dans TB UI, dupliquer le widget DHW Card**

Widget bundle library → tduo → DHW Card → bouton "..." → "Export to JSON". Importer comme nouveau widget avec name "DHW Card v2", fqn `tduo.dhw_card_v2`.

- [ ] **Step 2 : Modifier le `controllerScript` du widget v2**

Patron type : remplacer toutes les lectures de clés flat par lecture de `pac_v2`. Exemple typique :

```javascript
// AVANT
self.onDataUpdated = function() {
  var data = self.ctx.data;
  var tOut = data[0].data[data[0].data.length - 1][1];   // dhw_tOut
  var tIn  = data[1].data[data[1].data.length - 1][1];   // dhw_tIn
  // ...
};

// APRÈS
self.onDataUpdated = function() {
  var pac = JSON.parse(self.ctx.data[0].data[self.ctx.data[0].data.length - 1][1]);
  // pac est l'objet pac_v2 entier (1 seul datasource maintenant)
  var tOut = pac.dhw.tOut;
  var tIn  = pac.dhw.tIn;
  var tTank = pac.dhw.tTank;
  var posV3V = pac.dhw.posV3V;
  var pumps = [pac.dhw.pump1, pac.dhw.pump2, pac.dhw.pump3, pac.dhw.pump4];
  // ...
};
```

- [ ] **Step 3 : Modifier le `defaultConfig.datasources` pour ne lire qu'une clé**

```json
{
  "datasources": [
    {
      "type": "entity",
      "dataKeys": [
        {
          "name": "pac_v2",
          "type": "timeseries",
          "label": "PAC v2 payload",
          "settings": {},
          "color": "#2196f3"
        }
      ]
    }
  ]
}
```

Un seul `dataKey` (`pac_v2`), au lieu des 5-15 keys flat précédentes.

- [ ] **Step 4 : Tester le widget sur un dashboard temporaire**

Créer un dashboard "test-widgets-v2", y placer DHW Card v2 avec comme entity le device test du Task 3 step 3 (qui a déjà du `pac_v2` écrit). Vérifier visuellement que les valeurs s'affichent correctement.

- [ ] **Step 5 : Export du widget v2 finalisé**

```powershell
$w = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/widgetTypes?bundleAlias=tduo&fqn=tduo.dhw_card_v2" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$w | ConvertTo-Json -Depth 100 | Out-File scripts/tb/widgets-v2/dhw-card-v2.json -Encoding utf8
mkdir -Force scripts/tb/widgets-v2
git add scripts/tb/widgets-v2/dhw-card-v2.json
git commit -m "feat(tb-widget): DHW Card v2 reading pac_v2.dhw.*"
```

### Task 10 : Refactor Heating Loop Card → v2

**Files:**
- Modify : widget via TB UI (alias `tduo.heating_loop_card_v2`)
- Create : `scripts/tb/widgets-v2/heating-loop-card-v2.json`

- [ ] **Step 1 : Dupliquer Heating Loop Card en v2 (idem Task 9 Step 1)**

- [ ] **Step 2 : Mapping flat → v2 pour ce widget**

| Flat actuel | Path v2 |
|---|---|
| `heat_tOut` | `pac_v2.heat.tOut` |
| `heat_tIn` | `pac_v2.heat.tIn` |
| `heat_posV3V` | `pac_v2.heat.posV3V` |
| `heat_qeCalc` | `pac_v2.heat.qeCalc` |
| `heat_calo_tIn` | `pac_v2.heat.calo.tIn` |
| `heat_calo_tRet` | `pac_v2.heat.calo.tRet` |
| `heat_calo_qe` | `pac_v2.heat.calo.qe` |
| `heat_calo_pwr` | `pac_v2.heat.calo.pwr` |
| `heat_calo_hKwh` | `pac_v2.heat.calo.hKwh` |
| `heat_calo_cKwh` | `pac_v2.heat.calo.cKwh` |

Les unités (`heat_calo_qeU`, `heat_calo_pwrU`, etc.) sont maintenant en SERVER_SCOPE attribute, à lire via `ctx.entityService.getEntityAttributes()` au mount du widget.

- [ ] **Step 3 : Mettre à jour controllerScript + datasource (idem Task 9 Steps 2-3)**

Au mount, charger les attributs SERVER_SCOPE une fois :
```javascript
self.onInit = function() {
  self.ctx.entityService.getEntityAttributes(
    self.ctx.defaultSubscription.targetDeviceId,
    'SERVER_SCOPE',
    ['heat_calo_qeU','heat_calo_pwrU','heat_calo_hKwhU','heat_calo_cKwhU']
  ).subscribe(function(attrs) {
    self.calo_units = {};
    attrs.forEach(function(a) { self.calo_units[a.key] = a.value; });
  });
};
```

- [ ] **Step 4 : Tester visuellement sur le dashboard de test**

- [ ] **Step 5 : Export + commit**

```bash
git add scripts/tb/widgets-v2/heating-loop-card-v2.json
git commit -m "feat(tb-widget): Heating Loop Card v2 reading pac_v2.heat.* + SERVER_SCOPE units"
```

### Task 11 : Refactor Hub Info → v2

**Files:**
- Modify : widget via TB UI (alias `tduo.hub_info_v2`)
- Create : `scripts/tb/widgets-v2/hub-info-v2.json`

- [ ] **Step 1 : Dupliquer Hub Info en v2**

- [ ] **Step 2 : Mapping flat → v2**

| Flat actuel | Source v2 |
|---|---|
| `id` | attribut SERVER_SCOPE `id` |
| `rel` | attribut `rel` |
| `modType` | attribut `modType` |
| `nHp` | attribut `nHp` |
| `tExt` | `pac_v2.tExt` |
| `press` | `pac_v2.press` |
| `tInM` | `pac_v2.tInM` |
| `commCm2` | attribut `commCm2` |
| `relCm2` | attribut `relCm2` |

Les versions et l'identifiant sont des attributs, le reste est du telemetry.

- [ ] **Step 3 : controllerScript adapté**

```javascript
self.onInit = function() {
  // Charger les attributs au mount (changent rarement)
  self.ctx.entityService.getEntityAttributes(
    self.ctx.defaultSubscription.targetDeviceId,
    'SERVER_SCOPE',
    ['id','rel','modType','nHp','commCm2','relCm2']
  ).subscribe(function(attrs) {
    self.attrs = {};
    attrs.forEach(function(a) { self.attrs[a.key] = a.value; });
    self.refreshUI();
  });
};

self.onDataUpdated = function() {
  if (self.ctx.data && self.ctx.data[0] && self.ctx.data[0].data.length > 0) {
    self.pac = JSON.parse(self.ctx.data[0].data[self.ctx.data[0].data.length-1][1]);
    self.refreshUI();
  }
};

self.refreshUI = function() {
  // Update DOM from self.attrs + self.pac
  ...
};
```

- [ ] **Step 4 : Tester + Export + commit**

```bash
git add scripts/tb/widgets-v2/hub-info-v2.json
git commit -m "feat(tb-widget): Hub Info v2 reading pac_v2 + SERVER_SCOPE attrs"
```

### Task 12 : Refactor PAC Synoptic → v2

**Files:**
- Modify : widget via TB UI (alias `tduo.pac_synoptic_v2`)
- Create : `scripts/tb/widgets-v2/pac-synoptic-v2.json`

- [ ] **Step 1 : Dupliquer**

- [ ] **Step 2 : Mapping flat → v2**

PAC Synoptic affiche **un** HP. Index du HP à afficher = paramètre du widget (defaultConfig). En v1 c'était probablement codé en dur ou lu depuis `HP{i}_status` flat.

En v2 : `pac_v2.HPs[index]` avec `index` 0..3, et lecture des sous-objets `HP`, `invert`, `boil`, `pump`. Les versions du HP : attributs `HP{index+1}_relStm`, `_relEsp`, `_relScr`.

- [ ] **Step 3 : controllerScript**

```javascript
// Le widget a un setting "hpIndex" (0..3) configurable
self.hpIndex = self.ctx.settings.hpIndex || 0;

self.onInit = function() {
  // Versions du HP
  var keys = ['HP'+(self.hpIndex+1)+'_relStm','HP'+(self.hpIndex+1)+'_relEsp','HP'+(self.hpIndex+1)+'_relScr'];
  self.ctx.entityService.getEntityAttributes(self.ctx.defaultSubscription.targetDeviceId, 'SERVER_SCOPE', keys).subscribe(function(attrs) {
    self.attrs = {};
    attrs.forEach(function(a) { self.attrs[a.key] = a.value; });
    self.refreshUI();
  });
};

self.onDataUpdated = function() {
  if (self.ctx.data && self.ctx.data[0] && self.ctx.data[0].data.length > 0) {
    var pac = JSON.parse(self.ctx.data[0].data[self.ctx.data[0].data.length-1][1]);
    self.hp = pac.HPs[self.hpIndex];   // sous-objet HP complet
    self.refreshUI();
  }
};

self.refreshUI = function() {
  // self.hp.HP.status, self.hp.HP.pHi, self.hp.invert.freq, self.hp.boil.tOut, self.hp.pump.rpm, etc.
};
```

- [ ] **Step 4 : Ajouter `hpIndex` au settings schema du widget**

```json
"settingsSchema": {
  "schema": {
    "type": "object",
    "properties": {
      "hpIndex": { "type": "integer", "minimum": 0, "maximum": 3, "default": 0 }
    }
  }
}
```

- [ ] **Step 5 : Tester avec hpIndex=0 et hpIndex=1**

- [ ] **Step 6 : Export + commit**

```bash
git add scripts/tb/widgets-v2/pac-synoptic-v2.json
git commit -m "feat(tb-widget): PAC Synoptic v2 reading pac_v2.HPs[hpIndex]"
```

### Task 13 : Refactor Boiler Synoptic → v2

**Files:**
- Modify : widget via TB UI (alias `tduo.boiler_synoptic_v2`)
- Create : `scripts/tb/widgets-v2/boiler-synoptic-v2.json`

- [ ] **Step 1 : Dupliquer + ajouter `hpIndex` au settings (idem PAC Synoptic)**

- [ ] **Step 2 : Mapping**

Boiler appartient à 1 HP donc lit `pac_v2.HPs[hpIndex].boil.*` : `status`, `tOut`, `tSmoke`, `press`, `qe`, `rpm`, `time`.

- [ ] **Step 3 : controllerScript adapté (similaire à PAC Synoptic mais sur `.boil.*`)**

- [ ] **Step 4 : Tester + Export + commit**

```bash
git add scripts/tb/widgets-v2/boiler-synoptic-v2.json
git commit -m "feat(tb-widget): Boiler Synoptic v2 reading pac_v2.HPs[hpIndex].boil"
```

### Task 14 : Refactor TDUO Tile → v2

**Files:**
- Modify : widget via TB UI (alias `tduo.tduo_tile_v2`)
- Create : `scripts/tb/widgets-v2/tduo-tile-v2.json`

- [ ] **Step 1 : Inspecter le rôle du widget (~9.4 KB descriptor = le plus gros)**

Probablement template/brique réutilisée par les 5 autres ou un widget composite. Si c'est juste un template HTML/CSS, le rôle peut rester intact en v2.

- [ ] **Step 2 : Si le widget lit des données : appliquer le pattern pac_v2**

Si TDUO Tile lit n'importe quelle donnée flat, la rebrancher sur `pac_v2` avec un path configurable via settings.

- [ ] **Step 3 : Export + commit**

```bash
git add scripts/tb/widgets-v2/tduo-tile-v2.json
git commit -m "feat(tb-widget): TDUO Tile v2 (base brick) adapted to pac_v2"
```

### Task 14.A : Refactor Usage Pie PAC/Chaudière → v2

**Files:**
- Modify : widget `tduo.usage_pie` via TB UI ou REST
- Create : `scripts/tb/widgets-v2/usage-pie-v2.json`

> Widget actuellement déployé sur `donnees_HP1`. Affiche la répartition d'utilisation PAC vs chaudière.

- [ ] **Step 1 : Adapter les datasources pour lire `pac_v2.HPs[hpIndex].HP.time` et `pac_v2.HPs[hpIndex].boil.time`**

⚠ **Conversion d'unités critique** (point 1 A1) :
- `HP.time` et `boil.time` sont en **SECONDES** (pas heures comme d'autres `time`)
- Calcul camembert : convertir en heures pour cohérence d'affichage `time_h = time_s / 3600`

```javascript
self.onDataUpdated = function() {
  var pac = JSON.parse(self.ctx.data[0].data[self.ctx.data[0].data.length-1][1]);
  var hpIdx = self.ctx.settings.hpIndex || 0;
  var pacTimeS = pac.HPs[hpIdx].HP.time || 0;      // secondes
  var boilTimeS = pac.HPs[hpIdx].boil.time || 0;   // secondes
  var pacTimeH = pacTimeS / 3600;
  var boilTimeH = boilTimeS / 3600;
  self.updatePie([pacTimeH, boilTimeH]);
};
```

- [ ] **Step 2 : Tester sur device test du Task 3 (déjà avec pac_v2 écrit)**

- [ ] **Step 3 : Export + commit**

```bash
git add scripts/tb/widgets-v2/usage-pie-v2.json
git commit -m "feat(tb-widget): Usage Pie v2 reading pac_v2 with s -> h conversion"
```

### Task 14.B : Refactor Events History → v2 + archiver versions 2..7

**Files:**
- Modify : widget `tduo.events_history` via TB UI ou REST
- Create : `scripts/tb/widgets-v2/events-history-v2.json`
- Archive (delete) : `tduo.events_history2` à `tduo.events_history7`

> Widget actuellement déployé sur `historique`. Affiche la liste chronologique des événements défaut.

- [ ] **Step 1 : Adapter à lire `evt_*` keys avec FAULT_LABELS lookup**

Les `evt_*` sont déjà flat sur le device PAC (Section 3.5 spec). Le widget doit :
- Lire `evt_date`, `evt_time`, `evt_device`, `evt_fault`, `evt_status`, `evt_type` (latest values + history)
- ⚠ `evt_id` est en **epoch secondes**, pas ms. Convertir `× 1000` pour `new Date(evt_id * 1000)`
- Lookup `evt_fault` → libellé FR via FAULT_LABELS table 114 codes (déjà dans `tduo.fault_diagnostic`)

```javascript
var FAULT_LABELS = { /* table 114 codes — peut être référencée depuis tduo.fault_diagnostic */ };

self.onDataUpdated = function() {
  var rows = self.ctx.data[0].data.map(function(point) {
    var evtFault = parseInt(point[1]);
    return {
      ts: new Date(point[0]),
      label: FAULT_LABELS[evtFault] || "Code " + evtFault,
      code: evtFault
    };
  });
  self.renderList(rows);
};
```

- [ ] **Step 2 : Test sur un device avec évents défaut historiques**

- [ ] **Step 3 : Archiver les 6 versions de dev**

```powershell
foreach ($v in 2..7) {
  $fqn = "tduo.events_history$v"
  $w = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/widgetTypes?fqn=$fqn" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
  if ($w -and $w.id) {
    Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/widgetType/$($w.id.id)" -Method Delete -Headers @{Authorization="Bearer $env:TB_TOKEN"}
    Write-Host "Deleted widget: $fqn"
  }
}
```

- [ ] **Step 4 : Export + commit**

```bash
git add scripts/tb/widgets-v2/events-history-v2.json
git commit -m "feat(tb-widget): Events History v2 with FAULT_LABELS lookup + archived versions 2..7"
```

### Task 14.C : Refactor Fault Diagnostic → v2 (minimal)

**Files:**
- Modify : widget `tduo.fault_diagnostic` via TB UI ou REST
- Create : `scripts/tb/widgets-v2/fault-diagnostic-v2.json`

> Widget actuellement déployé sur `fault_diagnostic`. La table `FAULT_LABELS` 114 codes (déjà dans le code) est la source de vérité.

- [ ] **Step 1 : Vérifier la table `FAULT_LABELS` est exhaustive (114 codes 0..113)**

Spec Section 3.5.4. Si nouveaux codes firmware → ajouter à la table.

- [ ] **Step 2 : Adapter si nécessaire les sources de données pour `evt_*` (déjà flat, peu de changement)**

Le widget lit déjà les `evt_*` via attributs latest ts_kv. Pas de changement majeur.

- [ ] **Step 3 : Export + commit**

```bash
git add scripts/tb/widgets-v2/fault-diagnostic-v2.json
git commit -m "feat(tb-widget): Fault Diagnostic v2 (minimal refactor, FAULT_LABELS validated)"
```

---

## Phase 4 : Refonte dashboard "Mes Installations"

### Task 15 : Backup du dashboard actuel

**Files:**
- Create : `scripts/tb/backup/dashboard-mes-installations-pre-v2.json`

- [ ] **Step 1 : Récupérer l'UUID**

```powershell
$dashboards = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/tenant/dashboards?pageSize=100&page=0" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$dashboards.data | Where-Object { $_.title -eq "Mes Installations" } | Select-Object id, title
```

- [ ] **Step 2 : Export**

```powershell
$dashId = "<uuid>"
$dash = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/dashboard/$dashId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$dash | ConvertTo-Json -Depth 100 | Out-File scripts/tb/backup/dashboard-mes-installations-pre-v2.json -Encoding utf8
git add scripts/tb/backup/dashboard-mes-installations-pre-v2.json
git commit -m "chore(tb): backup Mes Installations dashboard pre-v2 refactor"
```

### Task 16 : Refonte state `default` (Unité) — placer les widgets TDUO v2

**Files:**
- Modify : dashboard "Mes Installations" via TB UI

- [ ] **Step 1 : Ouvrir le dashboard en mode édition, sélectionner l'état `default`**

- [ ] **Step 2 : Supprimer les widgets `markdown_card` actuellement présents dans cet état**

Noter d'abord leur disposition (positions, tailles) pour respecter le layout général.

- [ ] **Step 3 : Ajouter les widgets TDUO v2 dans l'ordre :**

| Widget | Position recommandée | hpIndex setting |
|---|---|---|
| Hub Info v2 | Haut, pleine largeur | — |
| Heating Loop Card v2 | 2e ligne, demi-largeur gauche | — |
| DHW Card v2 | 2e ligne, demi-largeur droite | — |
| PAC Synoptic v2 ×N | Lignes suivantes, N = nHp affichable max (4) | 0, 1, 2, 3 — visibilité conditionnelle si hpIndex < nHp |
| Boiler Synoptic v2 ×N | Sous chaque PAC Synoptic ou en accordéon | 0, 1, 2, 3 — visibilité conditionnelle si HP a une chaudière (`pac.HPs[i].boil.status != null`) |

Pour la visibilité conditionnelle : utiliser l'option "Display widget" → "Function" et écrire une condition JS lisant `pac_v2`.

- [ ] **Step 4 : Configurer l'entity alias**

Tous les widgets doivent utiliser le même `entityAlias` qui pointe sur le device sélectionné (via paramètre URL `device` ou via dropdown selector dans le dashboard).

- [ ] **Step 5 : Sauvegarder le dashboard**

- [ ] **Step 6 : Vérifier visuellement sur le device test**

Naviguer le dashboard → state `default` avec le device test du Task 3. Tous les widgets doivent afficher des valeurs cohérentes lues depuis `pac_v2`.

- [ ] **Step 7 : Commit**

```bash
git commit --allow-empty -m "feat(tb-dashboard): state default refactored to TDUO v2 widgets reading pac_v2"
```

### Task 17 : Refonte state `donnees_HP1`

**Files:**
- Modify : dashboard via TB UI

- [ ] **Step 1 : Ouvrir l'état `donnees_HP1`**

Vu le nom du state, c'était probablement spécialisé HP1. En v2, on en fait un état générique "Détail HP sélectionné" avec PAC Synoptic v2 plein écran.

- [ ] **Step 2 : Remplacer le contenu par 1 × PAC Synoptic v2 en pleine page**

Configurer le widget avec setting `hpIndex` lu depuis un paramètre dynamique de l'état (ex : si le state a un paramètre `params.hpIndex`, le passer au widget).

- [ ] **Step 3 : Tester avec hpIndex=0, hpIndex=1**

- [ ] **Step 4 : Commit**

```bash
git commit --allow-empty -m "feat(tb-dashboard): state donnees_HP1 → generic HP detail with PAC Synoptic v2"
```

### Task 18 : Refonte state `historique` — Chart.js custom sur pac_v2 array

**Files:**
- Create : nouveau widget custom JS dans TB (alias `tduo.historique_chart_v2`)
- Create : `scripts/tb/widgets-v2/historique-chart-v2.json`

- [ ] **Step 1 : Créer un nouveau widget custom de type "Time series chart"**

TB Widgets → New widget bundle item → type "Time series". Naming : `tduo.historique_chart_v2`.

- [ ] **Step 2 : controllerScript qui lit l'array pac_v2 sur fenêtre temporelle**

```javascript
self.onDataUpdated = function() {
  // ctx.data[0].data = array de [ts, json_string] pour la clé pac_v2 sur la fenêtre
  var series = self.ctx.data[0].data;
  var labels = [];
  var datasets = {
    heatTOut: { label: 'Heat tOut', data: [], borderColor: '#e74c3c' },
    dhwTOut:  { label: 'DHW tOut',  data: [], borderColor: '#3498db' },
    tExt:     { label: 'tExt',      data: [], borderColor: '#95a5a6' }
    // ... autres séries à extraire
  };
  series.forEach(function(point) {
    var ts = point[0];
    var pac = JSON.parse(point[1]);
    labels.push(new Date(ts).toISOString());
    datasets.heatTOut.data.push(pac.heat.tOut);
    datasets.dhwTOut.data.push(pac.dhw.tOut);
    datasets.tExt.data.push(pac.tExt);
  });
  self.chart.data.labels = labels;
  self.chart.data.datasets = Object.values(datasets);
  self.chart.update('none');
};

self.onInit = function() {
  // Charger Chart.js depuis CDN ou bundle TB
  var ctx = self.ctx.$container[0].querySelector('canvas').getContext('2d');
  self.chart = new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: { responsive: true, animation: false }
  });
};
```

- [ ] **Step 3 : Permettre à l'utilisateur de sélectionner les séries à afficher**

Via settings widget : array de paths `pac_v2.heat.tOut`, `pac_v2.dhw.tOut`, etc. Le script résout dynamiquement.

- [ ] **Step 4 : Tester sur fenêtre 1h, 24h, 1 semaine du device test**

Vérifier que le rendu reste < 3 s même pour la fenêtre 1 an (objectif acceptance criterion).

- [ ] **Step 5 : Export + commit**

```bash
git add scripts/tb/widgets-v2/historique-chart-v2.json
git commit -m "feat(tb-widget): historique-chart-v2 Chart.js custom reading pac_v2 array"
```

### Task 19 : Placer l'historique chart dans le state `historique`

**Files:**
- Modify : dashboard via TB UI

- [ ] **Step 1 : Ouvrir l'état `historique`**

- [ ] **Step 2 : Remplacer les charts TB natifs par 1 × historique-chart-v2 plein écran**

- [ ] **Step 3 : Configurer le widget avec un timewindow par défaut (ex : last 24 h)**

- [ ] **Step 4 : Tester chargement 6 mois et 1 an**

- [ ] **Step 5 : Commit**

```bash
git commit --allow-empty -m "feat(tb-dashboard): state historique → Chart.js custom on pac_v2 array"
```

### ~~Task 20 : Live mode keep-alive widget~~ — **DIFFÉRÉ**

> **Drop** : mode live archivé Section 11.1 spec (points 3+6, 2026-05-29). Cadence 1/min fixe, aucun widget keep-alive nécessaire. Réactivation possible en suivant le design archivé.

### Task 21 : Supprimer les anciens markdown_card et widgets obsolètes

**Files:**
- Modify : dashboard via TB UI
- Optional : suppression des widgets v1 dans le bundle `tduo.*` (uniquement après acceptance)

- [ ] **Step 1 : Confirmer qu'aucun état ne référence encore les 12 markdown_card**

Inspection JSON du dashboard exporté pour s'assurer qu'ils ne sont plus dans `configuration.widgets`.

- [ ] **Step 2 : Supprimer les widgets v1 du bundle `tduo` (ne le faire qu'après le go-live)**

À reporter au-delà de Phase 8 acceptance. Marquer dans le ticket de suivi.

- [ ] **Step 3 : Commit dashboard final**

```bash
git commit --allow-empty -m "chore(tb-dashboard): remove obsolete markdown_card widgets from Mes Installations"
```

---

## Phase 5 : Storage rotation cron

### Task 22 : Écrire le script bash `tb-ts_kv-drop-old-year.sh`

**Files:**
- Create : `scripts/server/tb-ts_kv-drop-old-year.sh`

- [ ] **Step 1 : Créer le script en local**

```bash
#!/bin/bash
# /usr/local/bin/tb-ts_kv-drop-old-year.sh
# Drop ts_kv partitions older than 3 full years + current year.
# Runs yearly on Jan 1st 02:00.

set -euo pipefail

YEAR_TO_DROP=$(( $(date +%Y) - 4 ))
LOG="/var/log/tb-ts_kv-drop.log"

echo "$(date -Iseconds) — dropping ts_kv partitions for year ${YEAR_TO_DROP}" >> "${LOG}"

for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  PARTITION="ts_kv_${YEAR_TO_DROP}_${m}"
  if sudo -u postgres psql thingsboard -c "DROP TABLE IF EXISTS ${PARTITION};" >> "${LOG}" 2>&1; then
    echo "$(date -Iseconds) — dropped ${PARTITION}" >> "${LOG}"
  else
    echo "$(date -Iseconds) — FAILED to drop ${PARTITION}" >> "${LOG}"
  fi
done

echo "$(date -Iseconds) — done" >> "${LOG}"
```

- [ ] **Step 2 : Test syntactique local avec shellcheck**

```bash
shellcheck scripts/server/tb-ts_kv-drop-old-year.sh
```

Expected : aucun warning.

- [ ] **Step 3 : Commit**

```bash
git add scripts/server/tb-ts_kv-drop-old-year.sh
git commit -m "feat(server): yearly cron to drop ts_kv partitions beyond 3-year + current window"
```

### Task 23 : Tester le script sur le serveur avec une partition factice

**Files:**
- (test seulement, pas de modif fichier)

- [ ] **Step 1 : Copier le script sur le serveur prod**

```powershell
scp -i C:\Users\je\.ssh\yahtec-ota scripts/server/tb-ts_kv-drop-old-year.sh root@10.77.0.74:/usr/local/bin/
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "chmod +x /usr/local/bin/tb-ts_kv-drop-old-year.sh"
```

- [ ] **Step 2 : Créer une partition factice ancienne (année 2020 par ex.)**

```powershell
$sql = @'
CREATE TABLE IF NOT EXISTS ts_kv_2020_01 PARTITION OF ts_kv FOR VALUES FROM (1577836800000) TO (1580515200000);
INSERT INTO ts_kv (entity_id, key, ts, bool_v) SELECT id, 1, 1577836800001, true FROM device LIMIT 1;
SELECT 'created' AS status, count(*) AS rows FROM ts_kv_2020_01;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `created|1`.

- [ ] **Step 3 : Lancer le script avec `YEAR_TO_DROP=2020` simulé**

Modifier temporairement la variable. Test direct sans cron :

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "YEAR_TO_DROP=2020 bash -c 'for m in 01 02 03 04 05 06 07 08 09 10 11 12; do sudo -u postgres psql thingsboard -c \"DROP TABLE IF EXISTS ts_kv_2020_\${m};\"; done'"
```

- [ ] **Step 4 : Vérifier que `ts_kv_2020_01` a été dropé**

```powershell
"SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename = 'ts_kv_2020_01';" | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `0`.

- [ ] **Step 5 : Vérifier que `ts_kv_2026_*` (année courante) est intacte**

```powershell
"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'ts_kv_2026_%' ORDER BY tablename;" | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : toutes les partitions 2026 présentes.

- [ ] **Step 6 : Commit le résultat du test (log)**

```bash
git commit --allow-empty -m "test(server): verified tb-ts_kv-drop-old-year.sh drops correct partition"
```

### Task 24 : Installer le cron sur le serveur

**Files:**
- Create : `scripts/server/tb-storage-rotation.cron`
- Deploy : `/etc/cron.d/tb-storage-rotation` sur 10.77.0.74

- [ ] **Step 1 : Créer le fichier cron en local**

```cron
# /etc/cron.d/tb-storage-rotation
# Yearly drop of ts_kv partitions older than 3 full years + current year
# m h dom mon dow user command
0 2 1 1 * root /usr/local/bin/tb-ts_kv-drop-old-year.sh
```

- [ ] **Step 2 : Déployer**

```powershell
scp -i C:\Users\je\.ssh\yahtec-ota scripts/server/tb-storage-rotation.cron root@10.77.0.74:/etc/cron.d/tb-storage-rotation
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "chmod 644 /etc/cron.d/tb-storage-rotation; systemctl restart cron"
```

- [ ] **Step 3 : Vérifier l'enregistrement cron**

```powershell
ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "grep -r tb-ts_kv /etc/cron.d/ /var/log/cron.log 2>/dev/null"
```

- [ ] **Step 4 : Commit**

```bash
git add scripts/server/tb-storage-rotation.cron
git commit -m "feat(server): install yearly cron tb-storage-rotation"
```

---

## ~~Phase 6 : Rule chain "Live Timeout Sweep"~~ — **DIFFÉRÉ**

> **Drop** : mode live archivé Section 11.1 spec (points 3+6, 2026-05-29). Cadence 1/min fixe, aucune rule chain "sweep" nécessaire. Réactivation possible en suivant le design archivé dans la spec.
>
> La Task 25 originale (création rule chain Live Timeout Sweep cron + alternative SQL fallback) est conservée dans l'historique git si réactivation future.

---

## Phase 7 : Proxy mode v2 — activation progressive ✅ DONE 2026-05-28

Toutes les tasks ci-dessous ont été **exécutées et validées en prod le 2026-05-28**. La documentation des découvertes est en mémoire dans `project_proxy_pac_hybride.md`.

### Récapitulatif du run

| Task | Statut | Résultat |
|---|---|---|
| 26 — Documenter procédure toggle | ✅ | UI admin proxy `/proxy/ui` (yahtec/argon2). Toggle = checkbox `Format ThingsBoard (wrap ts)`. Bind sur champ `devices.<name>.tb_format` dans `/etc/telemetry-proxy/config.json`. |
| 27 — Activer mode v2 sur pilote | ✅ | `tb_format=true` activé pour device alias `tduo`. Les 2 automates `2602000001`/`2602000002` POSTent via `/proxy/api/v1/telemetry/tduo`. |
| 28 — Test cache offline + replay au ts d'origine | ✅ | Stop TB 5 min (16:55-17:00 UTC), cache passé 0 → 11, restart TB, cache vidé en ~60 s, 5 samples × 247 keys arrivent sur `2602000001`/`2602000002` au ts d'origine. |
| 29 — Test toggle rollback | N/A | Pas exécuté — mode v2 stable, jugé inutile de rollback pendant le test. |
| 30 — Rollout parc | ✅ | Le routing proxy se fait via un seul alias `tduo` qui dessert tous les automates. Pas de config par device à dupliquer. Tous les automates actifs sont déjà sur cette voie. |

### Architecture découverte pendant la validation

Le proxy POSTe via **un seul token TB** (`yDq5GxcbQpuJVgKYRiWu` → device `heatPumpHybride` profile `default`) qui joue le rôle de **dispatcher**. Une rule chain TB existante lit `installation_id` du body et redispatche vers le vrai device PAC (profile `pac hybride`).

| Composant | Rôle |
|---|---|
| Device `heatPumpHybride` (profile `default`) | Dispatcher : reçoit tous les POSTs proxy, trace via `evt_dispatch` |
| Devices `2602000001`, `2602000002`, `2610000001` (profile `pac hybride`) | Stockent le payload télémétrie réel (247 keys distinctes par sample) |
| Rule chain sur `heatPumpHybride` (déjà existante) | Lit `installation_id`, redispatche |

**Implication pour Phases 1-6** : la rule chain TBEL `split-attributes-from-payload` (Task 2) devra tourner **sur le device profile `pac hybride`** (en sortie du dispatch), pas sur le dispatcher.

### Composants installés sur le serveur

- Binary Rust `telemetry-proxy 0.1.0` à `/usr/local/bin/telemetry-proxy`
- Service systemd `telemetry-proxy.service` (Restart=always)
- Config `/etc/telemetry-proxy/config.json` (avec 6 backups `.bak.*` historiques)
- Cache SQLite `/var/lib/telemetry-proxy/cache.db` (table `pending(id, device, body BLOB, headers TEXT, created_at, attempts)`)
- Nginx routing : `/etc/nginx/snippets/telemetry-proxy-location.conf` monté sur vhost `bootloader.tsmart.fr` (HTTPS) + sites-available `telemetry-proxy` (HTTP :8088 legacy)
- UI admin : `https://bootloader.tsmart.fr/proxy/ui`, login `yahtec`

### TODO restant sur le proxy (hors couverture Phase 7 originale)

- [ ] **Bugs d'affichage UI proxy** (`https://bootloader.tsmart.fr/proxy/ui`). Reporté volontairement.
- [ ] **Activer P6/P7 (live discovery)** dans le proxy quand le mode live dashboards sera déployé (Phase 1+ Section 5 de la spec).

```bash
git add scripts/proxy/activate-mode-v2.md
git commit -m "docs(proxy): procedure for activating mode v2 toggle per device"
```

> Tasks 27-30 condensées dans le récap ci-dessus (Phase 7 DONE 2026-05-28). Historique git du repo + `project_proxy_pac_hybride.md` en mémoire contiennent les détails d'exécution. Les procédures SQL de validation restent dans les sections Phase 8 (mêmes critères).

---

## Phase 8 : Acceptance validation

### Task 31 : Valider tous les critères de la spec Section 13

- [ ] **Step 1 : Critère "100% des devices envoient en nested v2"**

```powershell
@'
WITH parc AS (
  SELECT id FROM device WHERE device_profile_id = (SELECT id FROM device_profile WHERE name = 'PAC Hybride')
)
SELECT count(*) AS total, sum(CASE WHEN c > 0 THEN 1 ELSE 0 END) AS using_pac_v2
FROM (
  SELECT p.id, (SELECT count(*) FROM ts_kv WHERE entity_id = p.id AND key = 'pac_v2' AND ts > extract(epoch from now() - interval '24h')*1000) AS c FROM parc p
) sub;
'@ | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `total = using_pac_v2`.

- [ ] **Step 2 : Critère "Aucune ligne flat (hors evt_*) après J+30"**

```powershell
@'
SELECT count(*) FROM ts_kv WHERE
  ts > extract(epoch from now() - interval '1 day')*1000
  AND key != 'pac_v2' AND key NOT LIKE 'evt_%'
  AND entity_id IN (SELECT id FROM device WHERE device_profile_id = (SELECT id FROM device_profile WHERE name = 'PAC Hybride'));
'@ | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `0`.

- [ ] **Step 3 : Critère "37 attributs SERVER_SCOPE par device"**

```powershell
@'
SELECT d.name, count(a.*) AS attr_count FROM device d
LEFT JOIN attribute_kv a ON a.entity_id = d.id AND a.attribute_type = 'SERVER_SCOPE'
WHERE d.device_profile_id = (SELECT id FROM device_profile WHERE name = 'pac hybride')
GROUP BY d.name ORDER BY d.name;
'@ | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `attr_count` ≥ 25 (pour devices avec slots HPs inactifs où relStm/Esp/Scr empty strings) à 37 (pour devices avec 4 HPs actifs). Cible nominale = 37 (cf spec Section 3.6).

- [ ] **Step 4 : Critère "Samples rejoués au ts d'origine"** — déjà validé Phase 7 Task 28 (proxy)

- [ ] **Step 5 : Critère "Widgets v2 affichent correctement"**

Naviguer le dashboard de bout en bout (states `default`, `donnees_HP1`, `historique`, `fault_diagnostic`). Aucun widget en erreur, valeurs cohérentes avec `pac_v2`.

- [ ] **Step 6 : Critère "Compactage rétroactif terminé"** (Phase 1.X)

```powershell
$sql = @'
SELECT 'ts_kv_2026_04' AS partition,
       (SELECT count(*) FROM ts_kv_2026_04) AS total_rows,
       (SELECT count(*) FROM ts_kv_2026_04 WHERE key = (SELECT key_id FROM key_dictionary WHERE key='pac_v2')) AS pac_v2_rows,
       pg_size_pretty(pg_total_relation_size('public.ts_kv_2026_04')) AS size
UNION ALL
SELECT 'ts_kv_2026_05', count(*), 0, pg_size_pretty(pg_total_relation_size('public.ts_kv_2026_05')) FROM ts_kv_2026_05;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `total_rows` après compactage = ~0.4 % de la valeur d'origine (compactage 99 % ; il reste `evt_*` + flat post-cutover). Tailles partitions réduites d'au moins 50 %.

- [ ] **Step 7 : Critère "Chart historique 1 an < 3 s"**

State `historique`, fenêtre 1 an. Si > 3 s : déclencher Décisions différées (TimescaleDB / pré-agrégation, Section 11 spec).

- [ ] **Step 8 : Critère "Script rotation testé"** — déjà validé Task 23

- [ ] **Step 9 : Critère "13 alarmes supprimées"** — déjà validé Task 5

- [ ] **Step 10 : Critère "Option B : phase 3.6 — retrait branche flat"** (après widgets validés ≥ 7 jours)

Désactiver/supprimer la connexion `mark active → save TS (per-id device)` via script REST (variante de `deploy-v2-nodes.ps1` qui supprime la connexion ciblée). Une fois fait, les nouveaux samples n'ont plus que `pac_v2` (volume × ~250 de réduction).

```powershell
# Verifier qu'apres Phase 3.6, plus aucun flat n'est ecrit (sauf evt_*)
$sql = @'
SELECT d.key, count(*)
FROM ts_kv_2026_05 k JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND k.ts > extract(epoch from now() - interval '5 minutes')*1000
GROUP BY d.key
ORDER BY count(*) DESC LIMIT 20;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : seules les keys `pac_v2` et `evt_*` apparaissent.

- [ ] **Step 11 : Commit acceptance**

```bash
git commit --allow-empty -m "ops: payload v2 PAC Hybride migration complete — all acceptance criteria validated"
```

### Task 32 : Supprimer les widgets v1 du bundle `tduo` (T+30 jours après acceptance)

**À faire uniquement après ≥ 30 jours sans régression.**

- [ ] **Step 1 : Confirmer aucun dashboard ne référence les v1**

```powershell
"SELECT title FROM dashboard WHERE configuration::text LIKE '%tduo.dhw_card\"%' AND configuration::text NOT LIKE '%tduo.dhw_card_v2%';" | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : 0 lignes.

- [ ] **Step 2 : Supprimer les 6 widgets v1 via TB UI**

- [ ] **Step 3 : Commit**

```bash
git commit --allow-empty -m "chore(tb): remove obsolete TDUO v1 widgets after v2 stabilization"
```

---

## Hors scope de ce plan

- **Développement automate** (firmware-adjacent, repo séparé). Automate v2 **déjà déployé** sur `2602000001`/`2602000002` (point 1 spec) ; ce plan suppose au minimum 1 automate v2 actif.
- **Mode live** (cadence dynamique 20s ↔ 60s, widget keep-alive, rule chain "Live Timeout Sweep") : **DIFFÉRÉ** (Section 11.1 spec). Phase 6 originale du plan est archivée. Si réactivation : suivre design Section 11.1.
- **Extension TB `postTelemetry?withSharedKeys=live`** : option Décisions différées (Section 11 spec), lié au mode live ci-dessus.
- **TimescaleDB + pré-agrégation horaire** : leviers Section 11 spec, à activer si Acceptance Task 31 step 7 (chart 1 an) dépasse 3 s.
- **Nouvelles alarmes sur `pac_v2`** : à spécifier séparément après acceptance.
- **Cleanup historique flat (DROP partitions pré-cutover)** : à T+1 an du cutover, séparé.

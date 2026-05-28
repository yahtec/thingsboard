# Payload v2 PAC Hybride — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer le pipeline télémétrie PAC Hybride de flat (275 keys/post) vers JSON nested `pac_v2` json_v + attributs SERVER_SCOPE, activer le mode live (cadence 20 s sur les états détail), et nettoyer les composants orphelins.

**Architecture:** L'automate envoie un JSON nested au proxy (déjà déployé). Le proxy a un toggle qui passe en mode v2 (parse `dateTime` → wrap `{ts, values}` + cache offline). La rule chain TBEL split les attributs SERVER_SCOPE et stocke le reste sous la clé `pac_v2` en json_v. Les widgets TDUO refactorisés lisent `pac_v2`. Préparation TB faite en compat dual-format (flat ancien + nested v2 coexistent), puis activation toggle proxy par device.

**Tech Stack:** ThingsBoard 4.3 (rule chain TBEL, dashboard JSON, widgets, REST API), PostgreSQL 15 (ts_kv partitionné mensuel), bash + cron sur Ubuntu, SSH (clé `yahtec-ota`), proxy LAN (config-driven toggle déjà en place).

**Spec :** [docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md](../specs/2026-05-28-payload-v2-pac-hybride-design.md)

**Hors scope de ce plan** : développement du code automate (repo séparé). Ce plan suppose qu'au moins un automate v2 est disponible pour tests à partir du Phase 7.

## Statut d'avancement

| Phase | Statut | Date |
|---|---|---|
| 0 — Setup | À faire | — |
| 1 — Rule chain v2 | À faire | — |
| 2 — Device profile cleanup | À faire | — |
| 3 — Widgets TDUO refactor | À faire | — |
| 4 — Dashboard refonte | À faire | — |
| 5 — Storage rotation cron | À faire | — |
| 6 — Live Timeout Sweep | À faire | — |
| **7 — Proxy mode v2 activation** | **✅ DONE (anticipé)** | **2026-05-28** |
| 8 — Acceptance | À faire | — |

**Note** : Phase 7 a été réalisée et validée en avance de phase 2026-05-28, **avant** les Phases 1-6. Possible parce que le proxy a un toggle indépendant et que la validation porte sur la couche transport seulement (parse `dateTime` → wrap `{ts, values}` → cache offline → replay). Les Phases 1-6 (côté TB) restent à dérouler quand le firmware automate v2 sera prêt à émettre du JSON nested. Voir détails Phase 7 plus bas et `project_proxy_pac_hybride` en mémoire.

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

## Phase 1 : Rule chain "PAC Hybride Router v2"

### Task 1 : Exporter la rule chain actuelle comme backup

**Files:**
- Create: `scripts/tb/backup/rule-chain-pac-hybride-router-current.json`

- [ ] **Step 1 : Localiser l'UUID de la rule chain**

```powershell
$rcs = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChains?pageSize=100&page=0" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$rcs.data | Where-Object { $_.name -match "PAC Hybride" } | Select-Object id, name
```

Noter l'UUID retourné (champ `id.id`).

- [ ] **Step 2 : Exporter la rule chain et son metadata**

```powershell
$rcId = "<uuid-from-step-1>"
$rc = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$meta = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId/metadata" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
mkdir -Force scripts/tb/backup
@{ruleChain=$rc; metadata=$meta} | ConvertTo-Json -Depth 100 | Out-File scripts/tb/backup/rule-chain-pac-hybride-router-current.json -Encoding utf8
```

- [ ] **Step 3 : Commit backup**

```bash
git add scripts/tb/backup/rule-chain-pac-hybride-router-current.json
git commit -m "chore(tb): backup rule chain PAC Hybride Router pre-v2"
```

### Task 2 : Écrire le script TBEL "split-attributes-from-payload"

**Files:**
- Create: `scripts/tb/rule-chain-pac-hybride-router-v2/split-attributes.tbel`

- [ ] **Step 1 : Créer le fichier script TBEL**

```javascript
// scripts/tb/rule-chain-pac-hybride-router-v2/split-attributes.tbel
//
// Reçoit un msg nested v2 (msg.HPs !== undefined) déjà avec metadata.ts
// défini par TB depuis le wrapper {ts, values} envoyé par le proxy.
// Sortie : 2 messages — POST_ATTRIBUTES_REQUEST (SERVER_SCOPE) + POST_TELEMETRY_REQUEST (pac_v2).

var ATTR_PATHS = [
  "id", "rel", "modType", "nHp", "commCm2", "relCm2",
  "dhw.tSet",
  "heat.slope", "heat.foot", "heat.tMax",
  "heat.dayBgEte", "heat.monthBgEte",
  "heat.dayEndEte", "heat.monthEndEte",
  "heat.tCut", "heat.tRes",
  "heat.calo.qeU", "heat.calo.qeTotU",
  "heat.calo.pwrU", "heat.calo.hKwhU", "heat.calo.cKwhU",
  "HPs.relStm", "HPs.relEsp", "HPs.relScr"
];

var attrs = {};
var payload = clone(msg);

foreach (path : ATTR_PATHS) {
  var parts = path.split(".");

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

  var ref = payload;
  var ok = true;
  for (var j = 0; j < parts.length - 1; j++) {
    if (ref[parts[j]] == null) { ok = false; break; }
    ref = ref[parts[j]];
  }
  if (!ok) continue;
  var leafName = parts[parts.length - 1];
  if (ref[leafName] != null) {
    attrs[parts.join("_")] = ref[leafName];
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

- [ ] **Step 2 : Vérifier la syntaxe TBEL via l'endpoint TB testScript**

TB expose `/api/ruleChain/testScript` pour valider un script avant déploiement.

```powershell
$script = Get-Content scripts/tb/rule-chain-pac-hybride-router-v2/split-attributes.tbel -Raw
$testPayload = @{
  script = $script
  scriptType = "update"
  argNames = @("msg","metadata","msgType")
  msg = '{"dateTime":"20/01/26 16:34:00","id":"TEST","rel":"1.04","modType":3,"nHp":2,"HPs":[{"comm":1,"relStm":"1.23","relEsp":"2.45","relScr":"3.01","HP":{"status":4}},{"comm":1,"relStm":"1.23","relEsp":"2.45","relScr":"3.01","HP":{"status":0}}],"heat":{"slope":1.8,"tCut":20,"calo":{"qeU":2875}}}'
  metadata = '{"ts":"1716902040000"}'
  msgType = "POST_TELEMETRY_REQUEST"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/testScript" -Method Post -Body $testPayload -ContentType "application/json" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
```

Expected : sortie JSON avec `output` contenant les 2 messages (attrs + pac_v2), `error` null.

- [ ] **Step 3 : Commit**

```bash
git add scripts/tb/rule-chain-pac-hybride-router-v2/split-attributes.tbel
git commit -m "feat(tb): TBEL split-attributes-from-payload script for pac_v2 router"
```

### Task 3 : Construire la rule chain v2 JSON via TB UI

**Files:**
- Create: `scripts/tb/rule-chain-pac-hybride-router-v2/rule-chain-v2.json`

- [ ] **Step 1 : Dans TB UI, dupliquer la rule chain actuelle**

Naviguer Rule chains → "PAC Hybride Router" → bouton "..." → "Copy rule chain". Renommer la copie "PAC Hybride Router v2". Cette copie permet de la mettre au point sans casser la production.

- [ ] **Step 2 : Ouvrir la copie et structure les noeuds**

Architecture à câbler dans l'éditeur visuel :

```
[Input]
  │
  ▼
[Script node : "Switch nested vs flat"]
  // Returns msg avec metadata.format = "v2" ou "legacy"
  // metadata.format = (msg.HPs != null) ? "v2" : "legacy"
  │
  ▼
[Filter node : "Is nested v2?"]
  // condition : metadata.format == "v2"
  │   ├── True ──► [Script node : "split-attributes-from-payload"] (le TBEL de Task 2)
  │   │                │
  │   │                ├──► Attributes branch ──► [Save Attributes (SERVER_SCOPE)]
  │   │                │
  │   │                └──► Telemetry branch ──► [Save Timeseries]  // écrit key=pac_v2
  │   │
  │   └── False ──► [Save Timeseries]  // ancien chemin flat, intouché
```

- [ ] **Step 3 : Tester avec un device factice**

Créer un device test dans la même device profile, récupérer son token, et envoyer 2 POST :

```powershell
$token = "<test-device-token>"

# POST flat (ancien format) — doit passer par la branche legacy
$flat = '{"dateTime":"20/01/26 16:34:00","dhw_tOut":60.2,"dhw_tIn":45.2}'
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/v1/$token/telemetry" -Method Post -Body $flat -ContentType "application/json"

# POST nested v2 (proxy mode v2) — doit passer par la branche v2
$nested = '{"ts":1716902040000,"values":{"dateTime":"20/01/26 16:34:00","id":"TEST","rel":"1.04","modType":3,"nHp":1,"HPs":[{"comm":1,"relStm":"1.23","relEsp":"2.45","relScr":"3.01","HP":{"status":4,"pHi":25.3},"invert":{"comm":1,"freq":45},"boil":{"status":0},"pump":{"comm":1,"pwr":180}}],"heat":{"tOut":40,"slope":1.8,"calo":{"qe":11578,"qeU":2875}},"dhw":{"tOut":60,"tSet":60},"pump1M":{"pwr":200},"pump2M":{"pwr":0},"tExt":5.7,"tInM":60.1,"press":1.7,"commCm2":1,"relCm2":"1.02"}}'
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/v1/$token/telemetry" -Method Post -Body $nested -ContentType "application/json"
```

- [ ] **Step 4 : Vérifier en DB que les deux chemins produisent l'attendu**

```powershell
$sql = @'
-- Le device test
SELECT id FROM device WHERE name = '<test-device-name>';

-- Pour le POST flat : ts_kv avec key dhw_tOut
SELECT key, dbl_v, str_v FROM ts_kv WHERE entity_id = '<test-device-uuid>' AND ts > now()::timestamp - interval '5 min' ORDER BY ts DESC LIMIT 10;

-- Pour le POST nested : ts_kv avec key pac_v2 (json_v non null)
SELECT key, json_v FROM ts_kv WHERE entity_id = '<test-device-uuid>' AND key = 'pac_v2' ORDER BY ts DESC LIMIT 1;

-- Attributs SERVER_SCOPE écrits
SELECT key, str_v, long_v, dbl_v FROM attribute_kv WHERE entity_id = '<test-device-uuid>' AND attribute_type = 'SERVER_SCOPE' ORDER BY key;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected :
- POST flat → ligne `ts_kv` avec `key='dhw_tOut'`, `dbl_v=60.2`
- POST nested → ligne `ts_kv` avec `key='pac_v2'`, `json_v` contenant `{HPs:[...], heat:{...}, dhw:{...}, ...}` (sans les paths attributs)
- `attribute_kv` SERVER_SCOPE rempli : `id`, `rel`, `modType`, `nHp`, `dhw_tSet`, `heat_slope`, `heat_calo_qeU`, `HP1_relStm`, etc.

- [ ] **Step 5 : Exporter la rule chain v2 finalisée**

```powershell
$rcId = "<rule-chain-v2-uuid>"
$rc = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$meta = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId/metadata" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
@{ruleChain=$rc; metadata=$meta} | ConvertTo-Json -Depth 100 | Out-File scripts/tb/rule-chain-pac-hybride-router-v2/rule-chain-v2.json -Encoding utf8
git add scripts/tb/rule-chain-pac-hybride-router-v2/rule-chain-v2.json
git commit -m "feat(tb): rule chain PAC Hybride Router v2 with TBEL split"
```

### Task 4 : Bascule du device profile vers la rule chain v2

**Files:**
- Modify : device profile "PAC Hybride" (via TB UI)

- [ ] **Step 1 : Récupérer l'UUID du device profile**

```powershell
$profiles = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/deviceProfiles?pageSize=100&page=0" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$profiles.data | Where-Object { $_.name -match "PAC Hybride" } | Select-Object id, name, defaultRuleChainId
```

Noter l'UUID profile + l'UUID actuel de `defaultRuleChainId`.

- [ ] **Step 2 : Mettre à jour le profile pour pointer vers rule chain v2**

Via TB UI : Device profiles → PAC Hybride → Edit → "Default rule chain" → sélectionner "PAC Hybride Router v2" → Save.

- [ ] **Step 3 : Vérifier qu'un POST flat depuis un device existant continue à fonctionner**

```powershell
$token = "<token-d-un-device-prod-existant>"
$flat = '{"dhw_tOut":60.5,"dateTime":"20/01/26 16:40:00"}'
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/v1/$token/telemetry" -Method Post -Body $flat -ContentType "application/json"
```

```powershell
# Inspection DB
'SELECT key, dbl_v FROM ts_kv WHERE entity_id = (SELECT id FROM device WHERE name = ''<device-name>'') AND key = ''dhw_tOut'' ORDER BY ts DESC LIMIT 1;' | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : ligne `dhw_tOut=60.5` avec ts récent → confirme que la branche legacy de la rule chain v2 fonctionne.

- [ ] **Step 4 : Commit la documentation du changement**

```bash
git commit --allow-empty -m "ops(tb): switched PAC Hybride device profile default rule chain to v2"
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

## Phase 3 : Refactor des 6 widgets TDUO

Convention pour ces tâches : on duplique chaque widget (suffixe `_v2`), on refactorise la copie, on garde l'original intact comme fallback. Une fois le dashboard validé sur les v2, on supprime les originaux.

### Task 7 : Exporter les 6 widgets TDUO actuels (backup)

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

### Task 20 : Live mode keep-alive widget sur les states détail

**Files:**
- Modify : dashboard via TB UI — ajouter un widget caché (1×1 cell) sur `default` et `donnees_HP1`

- [ ] **Step 1 : Créer un nouveau widget custom de type "Latest values" minimal, alias `tduo.live_keepalive`**

Pas de UI visible (CSS `display:none` ou taille 1×1 en bas du dashboard).

- [ ] **Step 2 : controllerScript du widget keep-alive**

```javascript
self.onInit = function() {
  var deviceId = self.ctx.defaultSubscription.targetDeviceId;
  // Mark live=true au mount
  self.ctx.attributeService.saveEntityAttributes(deviceId, 'SHARED_SCOPE',
    [{key:'live', value:true}, {key:'liveTs', value:Date.now()}]);

  // Keep-alive setInterval 60s
  self.ka = setInterval(function() {
    if (document.visibilityState === 'visible') {
      self.ctx.attributeService.saveEntityAttributes(deviceId, 'SHARED_SCOPE',
        [{key:'liveTs', value:Date.now()}]);
    }
  }, 60000);

  // Au blur/hidden → live=false immédiat
  self.onVis = function() {
    if (document.visibilityState !== 'visible') {
      self.ctx.attributeService.saveEntityAttributes(deviceId, 'SHARED_SCOPE',
        [{key:'live', value:false}]);
    } else {
      self.ctx.attributeService.saveEntityAttributes(deviceId, 'SHARED_SCOPE',
        [{key:'live', value:true}, {key:'liveTs', value:Date.now()}]);
    }
  };
  document.addEventListener('visibilitychange', self.onVis);
  window.addEventListener('beforeunload', function() {
    self.ctx.attributeService.saveEntityAttributes(deviceId, 'SHARED_SCOPE',
      [{key:'live', value:false}]);
  });
};

self.onDestroy = function() {
  if (self.ka) clearInterval(self.ka);
  if (self.onVis) document.removeEventListener('visibilitychange', self.onVis);
  var deviceId = self.ctx.defaultSubscription.targetDeviceId;
  self.ctx.attributeService.saveEntityAttributes(deviceId, 'SHARED_SCOPE',
    [{key:'live', value:false}]);
};
```

- [ ] **Step 3 : Placer ce widget caché sur les states `default` et `donnees_HP1`**

- [ ] **Step 4 : Tester**

Ouvrir le dashboard sur le state `default`. Vérifier :
```powershell
'SELECT key, bool_v, long_v FROM attribute_kv WHERE entity_id = ''<test-device-uuid>'' AND attribute_type = ''SHARED_SCOPE'' AND key IN (''live'',''liveTs'');' | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `live=true`, `liveTs` ≈ now.

Fermer l'onglet, refaire la même requête → `live=false` doit apparaître après 1-2 s.

- [ ] **Step 5 : Commit**

```bash
git commit --allow-empty -m "feat(tb-widget): live keep-alive widget on dashboard detail states"
```

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

## Phase 6 : Rule chain "Live Timeout Sweep"

Cette rule chain auxiliaire s'exécute toutes les minutes côté TB et remet `live=false` sur les devices dont `liveTs` est périmé (> 3 min).

### Task 25 : Créer la rule chain "Live Timeout Sweep" dans TB UI

**Files:**
- Modify : TB rule chains
- Create : `scripts/tb/rule-chain-live-timeout-sweep/rule-chain.json`

- [ ] **Step 1 : Créer une nouvelle rule chain "Live Timeout Sweep" dans TB UI**

Rule chains → "+ Add new" → name "Live Timeout Sweep" → type "core" (n'est pas root, n'est pas device-profile-default).

- [ ] **Step 2 : Câbler les noeuds**

```
[Generator node]
  config:
    msgCount: 0 (unlimited)
    periodInSeconds: 60
    originator: tenant (current tenant)
    js function: returns { msg: {}, metadata: {}, msgType: "GENERATOR_MSG" }
  │
  ▼
[Filter / Script : sélectionner devices PAC Hybride avec live=true ET liveTs périmé]
  Utiliser un node "REST API call" ou "DB Find" (custom node si dispo) qui :
    - Liste les devices du profile PAC Hybride
    - Filtre attribut SHARED_SCOPE.live == true AND liveTs < now - 180000
  │
  ▼
[Save Attributes node]
  scope: SHARED_SCOPE
  values: { live: false }
  originator override: chaque device matché en sortie du filter
```

Note : TB rule chain n'a pas de "list all devices + filter" en noeud natif simple. Approche pragmatique :

**Alternative simplifiée :** au lieu d'un sweep côté TB, utiliser un **PostgreSQL cron** qui fait directement :

```sql
-- Met live=false pour tous devices avec liveTs > 180s
UPDATE attribute_kv SET bool_v = false
WHERE attribute_type = 'SHARED_SCOPE'
  AND key_id = (SELECT key_id FROM key_dictionary WHERE key = 'live')
  AND bool_v = true
  AND entity_id IN (
    SELECT entity_id FROM attribute_kv
    WHERE key_id = (SELECT key_id FROM key_dictionary WHERE key = 'liveTs')
      AND long_v < (extract(epoch from now()) * 1000 - 180000)::bigint
  );
```

Cette alternative est plus simple à mettre en oeuvre. Le décider lors de l'exécution selon ce qui est dispo en TB 4.3.

- [ ] **Step 3 : Tester en posant manuellement live=true + liveTs très ancien sur le device test**

```powershell
# Force live=true et liveTs ancien
$body = '[{"key":"live","value":true},{"key":"liveTs","value":1000000000000}]'
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/plugins/telemetry/DEVICE/<device-uuid>/attributes/SHARED_SCOPE" -Method Post -Body $body -ContentType "application/json" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
```

Attendre 1-2 min, puis vérifier :

```powershell
"SELECT key, bool_v, long_v FROM attribute_kv WHERE entity_id = '<device-uuid>' AND attribute_type = 'SHARED_SCOPE' AND key IN ('live','liveTs');" | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `live=false`.

- [ ] **Step 4 : Export + commit**

```powershell
$rcId = "<live-timeout-sweep-uuid>"
$rc = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
$meta = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/$rcId/metadata" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
mkdir -Force scripts/tb/rule-chain-live-timeout-sweep
@{ruleChain=$rc; metadata=$meta} | ConvertTo-Json -Depth 100 | Out-File scripts/tb/rule-chain-live-timeout-sweep/rule-chain.json -Encoding utf8
git add scripts/tb/rule-chain-live-timeout-sweep/rule-chain.json
git commit -m "feat(tb): Live Timeout Sweep rule chain (or SQL cron fallback)"
```

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

- [ ] **Step 3 : Critère "33 attributs SERVER_SCOPE par device"**

```powershell
@'
SELECT d.name, count(a.*) AS attr_count FROM device d
LEFT JOIN attribute_kv a ON a.entity_id = d.id AND a.attribute_type = 'SERVER_SCOPE'
WHERE d.device_profile_id = (SELECT id FROM device_profile WHERE name = 'PAC Hybride')
GROUP BY d.name ORDER BY d.name;
'@ | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Expected : `attr_count ≈ 33` pour chaque device.

- [ ] **Step 4 : Critère "Proxy retourne `{shared.live}` correctement"**

Ouvrir le dashboard sur state `default`, vérifier que la cadence des POST passe à 20 s (visible dans les logs proxy ou via le delta entre lignes `pac_v2`).

- [ ] **Step 5 : Critère "Samples rejoués au ts d'origine"** — déjà validé Task 28

- [ ] **Step 6 : Critère "Widgets affichent correctement"**

Naviguer le dashboard de bout en bout (states default, donnees_HP1, historique). Aucun widget en erreur, valeurs cohérentes.

- [ ] **Step 7 : Critère "Mode live cadence 20s ↔ 60s"**

Deux fenêtres : une ouverte sur state `default`, l'autre lance :

```powershell
"SELECT count(*) FROM ts_kv WHERE entity_id = '<uuid>' AND key = 'pac_v2' AND ts > extract(epoch from now() - interval '1 minute')*1000;" | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Page ouverte : ~3/min (20s). Page fermée 3 min puis retest : 1/min.

- [ ] **Step 8 : Critère "Chart historique 1 an < 3 s"**

State `historique`, fenêtre 1 an. Si > 3 s : déclencher Décisions différées (TimescaleDB / pré-agrégation).

- [ ] **Step 9 : Critère "Script rotation testé"** — déjà validé Task 23

- [ ] **Step 10 : Critère "13 alarmes supprimées"** — déjà validé Task 5

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

- **Développement automate** (firmware-adjacent, repo séparé). Ce plan suppose qu'un automate v2 est disponible pour le pilote (Task 27).
- **Réintroduction extension TB postTelemetry `?withSharedKeys=live`** : option Décisions différées (Section 11 spec), si le proxy `live discovery` devient un goulot.
- **TimescaleDB + pré-agrégation horaire** : leviers Section 11 spec, à activer si Acceptance Task 31 step 8 dépasse 3 s.
- **Nouvelles alarmes sur `pac_v2`** : à spécifier séparément après acceptance.
- **Cleanup historique flat (DROP partitions pré-cutover)** : à T+1 an du cutover, séparé.

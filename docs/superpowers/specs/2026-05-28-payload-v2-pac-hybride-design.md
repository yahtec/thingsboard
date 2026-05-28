# Payload v2 PAC Hybride — Design

**Date** : 2026-05-28
**Auteurs** : Julien (product), Claude (design)
**Statut** : Brouillon, en attente de validation utilisateur avant plan d'implémentation
**Branche** : `yahtec-main`

## 1. Contexte

ThingsBoard reçoit aujourd'hui des POST de télémétrie **flat** (~275 keys par message) de la part des PAC Hybrides. Mesures du 21-22 mai 2026 :

- 158.7 octets par ligne `ts_kv` (heap + PK btree)
- ~43 KB stockés / post pour 5 KB d'HTTP body (ratio ×8.6, le PK btree pèse plus que la donnée)
- 38% des keys envoyées ne sont jamais lues par les widgets
- Volume `ts_kv_2026_05` à 7.1 GB au 27 mai, +180 MB/jour, dominé à 59% par un seul device
- Extrapolation linéaire : 250 GB / an pour 10 PACs, 750 GB / an pour 30 PACs

Le plan de stockage (memo [project-thingsboard-storage-optim]) a acté une migration vers `json_v` + attributs SERVER_SCOPE, gain stockage ×13.

Ce document spécifie **le contrat firmware → TB**, **le routing rule chain**, **le mode live**, **la refonte dashboard**, **la rotation stockage**, et **les exigences firmware** pour la v2.

## 2. Goals & non-goals

### Goals

- Définir le contrat JSON nested envoyé par firmware (1 POST = 1 ligne `ts_kv` au lieu de 275)
- Spécifier la rule chain "PAC Hybride Router v2" qui split telemetry / attributs SERVER_SCOPE
- Permettre une cadence dynamique 1 post/min (normal) ↔ 1 post/20 s (mode live quand un client regarde)
- Refactorer les 6 widgets TDUO existants pour lire le nouveau payload
- Acter la rotation stockage : 3 ans glissants + année en cours, via DROP PARTITION mensuelle
- Cutover **par device** via OTA (pas de flag day global)

### Non-goals

- Refonte du flux `evt_*` (apparition/résolution de défauts) : reste flat, intouché
- Modification des widgets `events_history`, `fault_diagnostic`, `system.map`, iframes admin
- Migration vers TimescaleDB (gardé en réserve)
- Pré-agrégation horaire (gardé en réserve)
- Pré-agrégation des cumuls `hKwh`, `cKwh`, `qeTot` (déjà cumulatifs par nature)
- Mise en place d'un SHARED_SCOPE pour les setpoints (firmware = master, modifs hors TB)

## 3. Schéma v2 — contrat firmware → TB

### Endpoint

```
POST /api/v1/{deviceAccessToken}/telemetry
Content-Type: application/json
```

Un seul body JSON, structure nested décrite ci-dessous. Pas de pretty-print.

### Structure nested

```yaml
Chaufferie:
  dateTime: "20/01/26 16:34:00"   # JJ/MM/AA HH:MM:SS (24h, slash, espace, deux-points)
  id:        "2503200123"         # [ATTR] série device
  rel:       "1.04"               # [ATTR] version programme CPU principal
  modType:   3                     # [ATTR] enum 0..3
                                   #   0 = no module, 1 = heating, 2 = dhw, 3 = heating + dhw
  tExt:      5.7                   # °C température extérieure
  tInM:      60.1                  # °C température collecteur primaire
  press:     1.7                   # bar pression hydraulique primaire
  commCm2:   1                     # [ATTR] enum 0..1 comm carte CM2
  relCm2:    "1.02"                # [ATTR] version programme CM2

  pump1M:                          # pompe primaire 1
    pwr:  200                      # W puissance électrique
    dP:   7.5                      # mCE delta pression
    qe:   3.0                      # m³/h débit eau
    rpm:  4555                     # rpm vitesse
    time: 4000                     # h temps cumulé ON
  pump2M:                          # pompe primaire 2 (idem pump1M)
    pwr: 0; dP: 0; qe: 0; rpm: 0; time: 4000

  dhw:                              # bloc ECS, toujours présent (à 0 si modType ne contient pas DHW)
    tOut:    60.2                   # °C sortie ECS
    tIn:     45.2                   # °C entrée ECS
    tTank:   59.2                   # °C ballon ECS
    tSet:    60                     # [ATTR] °C consigne ECS
    posV3V:  100                    # % position V3V ECS primaire
    pump1:   { pwr, dP, qe, rpm, time }    # secondaire ECS pompe 1
    pump2:   { pwr, dP, qe, rpm, time }
    pump3:   { pwr, dP, qe, rpm, time }
    pump4:   { pwr, dP, qe, rpm, time }

  heat:                             # bloc chauffage, toujours présent (à 0 si modType ne contient pas heating)
    tOut:        40.2               # °C sortie chauffage
    tIn:         33.2               # °C retour chauffage
    posV3V:      100                # % position V3V chauffage
    qeCalc:      5000               # l/h débit estimé
    slope:       1.80               # [ATTR] pente loi de chauffe
    foot:        20                 # [ATTR] °C pied de pente
    tMax:        85                 # [ATTR] °C consigne max
    dayBgEte:    31                 # [ATTR] JJ début été
    monthBgEte:  5                  # [ATTR] MM début été
    dayEndEte:   31                 # [ATTR] JJ fin été
    monthEndEte: 9                  # [ATTR] MM fin été
    tCut:        20                 # [ATTR] °C température extérieure arrêt chauffage
    tRes:        17                 # [ATTR] °C température extérieure restart chauffage
    calo:                           # calorimètre Modbus
      tIn:    55.85                 # °C entrée
      tRet:   44.05                 # °C retour
      qe:     11578                 # débit (unité = qeU)
      qeU:    2875                  # [ATTR] code unité débit (2875 = l/h)
      qeTot:  456789                # cumul débit (unité = qeTotU)
      qeTotU: 3092                  # [ATTR] code unité cumul (3092 = 0.01 m³)
      pwr:    250                   # puissance (unité = pwrU)
      pwrU:   2860                  # [ATTR] code unité puissance (2860 = 10 W)
      hKwh:   123456                # énergie chaud (unité = hKwhU)
      hKwhU:  3078                  # [ATTR] code unité (3078 = kWh, 3079 = 10 kWh)
      cKwh:   654321                # énergie froid (unité = cKwhU)
      cKwhU:  3079                  # [ATTR] code unité

  HPs:                              # array de longueur = nb HP réellement présents (0..4)
    - comm:   1                     # enum 0..1
      relStm: "1.23"                # [ATTR] version STM32
      relEsp: "2.45"                # [ATTR] version ESP
      relScr: "3.01"                # [ATTR] version écran
      HP:
        status: 10                  # code statut HP (0=OFF, 1=attente débit, 4=ON, ...)
        pHi:    25.3                # bar haute pression
        pLo:    6.8                 # bar basse pression
        pAir:   120                 # Pa pression air
        tIn:    45.2                # °C entrée eau
        tOut:   52.7                # °C sortie eau
        tHPf:   8.5                 # °C HP froide
        tHPc:   65.4                # °C HP chaude
        tLP:    2.3                 # °C basse pression
        tCond:  48.1                # °C condensation
        tEvap:  -1.8                # °C évaporation
        tSC:    5.6                 # °C sous-refroidissement
        tOH:    12.4                # °C surchauffe
        eevPos: 800                 # pas vanne expansion (renommé depuis 'dpf')
        rpm:    850                 # rpm ventilateur
        time:   12450               # h temps cumulé HP ON
      invert:
        comm: 1                     # enum 0..1
        freq: 45                    # Hz fréquence sortie
        volt: 380.0                 # V tension sortie
        curr: 12.5                  # A courant sortie
        pwr:  4500                  # W puissance sortie
        def0: 0                     # code défaut 0
        def1: 0                     # code défaut 1
        def2: 0                     # code défaut 2
      boil:                         # chaudière appoint optionnelle par HP
        status: 0                   # 0=OFF, 5=ON, 8=défaut, ...
        tOut:   62.3                # °C sortie
        tSmoke: 180.5               # °C fumées
        press:  1.85                # bar pression eau
        qe:     1200                # l/h débit
        rpm:    4500                # rpm brûleur
        time:   3200                # h temps ON
      pump:                          # pompe individuelle HP
        comm: 1
        pwr:  180
        dP:   6.2
        qe:   2.8
        rpm:  4200
        time: 3800
```

### Marquage `[ATTR]`

Les champs marqués `[ATTR]` ci-dessus sont **routés en attribut SERVER_SCOPE** par la rule chain (Section 4). Le firmware **envoie tous ces champs à chaque cycle** ; TB déduplique côté `attribute_kv` (no-op si valeur identique au stockage actuel).

Total des champs routés en attribut par device :

| Catégorie | Nb champs | Notes |
|---|---|---|
| Métadonnées (id, rel, modType, commCm2, relCm2) | 5 | au root |
| Consignes heat (slope, foot, tMax, jours/mois été ×4, tCut, tRes) | 9 | sous `heat` |
| Consigne dhw (tSet) | 1 | sous `dhw` |
| Unités calo (qeU, qeTotU, pwrU, hKwhU, cKwhU) | 5 | sous `heat.calo` |
| Versions par HP (relStm, relEsp, relScr) × N HPs (max 4) | 3..12 | sous `HPs[].` |
| **Total max** | **32** | pour 4 HPs |

### Modifications vs schéma initial (mémoire utilisateur)

| Changement | Avant | Après |
|---|---|---|
| Date+heure | 2 strings `date` + `time` | 1 string combiné `dateTime` |
| Type module (root) | `type` (mot réservé certains langages) | `modType` |
| Nombre HP | `nHp` explicite | supprimé, déduit de `HPs.length` |
| Vanne expansion | `dpf` (peu clair) | `eevPos` |
| Bugs YAML | tabs au lieu d'espaces sur `posV3V` (dhw), `pump3` (dhw) | espaces |
| Routing | tout en ts_kv flat | nested, rule chain extrait 32 paths en SERVER_SCOPE |

### Format `dateTime`

L'automate formate avec `sprintf("%02d/%02d/%02d %02d:%02d:%02d", jour, mois, annee%100, heure, minute, seconde)`.

- Séparateur : `/` entre date, `:` entre heure, espace entre date et heure
- Année sur 2 chiffres (modulo 100)
- Pas d'offset timezone (local time du site)
- Sert de label humain dans le payload, **TB met son propre ts epoch ms** à réception qui sert d'axe temporel pour les graphes

### Contraintes encodage

- JSON sans pretty-print (pas de retours ligne ni d'espaces superflus)
- UTF-8
- Float 1 décimale max (sauf `rel`, `relCm2`, `relStm`, `relEsp`, `relScr` qui sont des strings du genre `"1.04"`)
- Booléens encodés `0` / `1` en integer (pas `true` / `false`)

## 4. Rule chain "PAC Hybride Router v2"

### Flow

```
Device telemetry POST
    │
    ▼
[Originator filter: device profile = PAC Hybride]
    │
    ▼
[Switch script: msg.HPs !== undefined ?]
    │
    ├── true (POST nested v2)
    │     │
    │     ▼
    │   [TBEL transform: split-attributes-from-payload]
    │     │   → 2 messages :
    │     │     • POST_ATTRIBUTES_REQUEST  (msg.attrs, scope=SERVER_SCOPE)
    │     │     • POST_TELEMETRY_REQUEST   ({ pac_v2: <payload sans attrs> })
    │     │
    │     ├── POST_ATTRIBUTES_REQUEST ─► [Save Attributes node, scope=SERVER_SCOPE]
    │     │
    │     └── POST_TELEMETRY_REQUEST ──► [Save Timeseries node, useServerTs=false]
    │                                       (1 ligne ts_kv, key="pac_v2", value_json=<payload>)
    │
    └── false (POST flat : evt_* ou ancien firmware)
          │
          ▼
        [Save Timeseries node, default flat]
          → chemin actuel, intouché
```

### Script TBEL "split-attributes-from-payload"

```javascript
// Paths à router en SERVER_SCOPE. Sup HPs.* applique sur chaque élément.
var ATTR_PATHS = [
  "id", "rel", "modType", "commCm2", "relCm2",
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
var payload = clone(msg);  // TBEL : clone() au lieu de JSON.parse(JSON.stringify())

foreach (path : ATTR_PATHS) {
  var parts = path.split(".");

  // Cas spécial : HPs.* (array)
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

  // Cas générique dotted path
  var ref = payload;
  for (var j = 0; j < parts.length - 1; j++) {
    if (ref[parts[j]] == null) { break; }
    ref = ref[parts[j]];
  }
  var leafName = parts[parts.length - 1];
  if (ref != null && ref[leafName] != null) {
    var attrKey = parts.join("_");  // heat.calo.qeU -> heat_calo_qeU
    attrs[attrKey] = ref[leafName];
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

> **Note implémentation** : la syntaxe TBEL exacte (`foreach`, `.remove()`, `metadata.merge()`) doit être validée contre la doc TB 4.3. Si une primitive manque, fallback vers le node JavaScript équivalent (légèrement plus lent mais sémantique identique).

### Nommage

- **Clé telemetry** : `pac_v2` (string fixe, versionnée — permet l'évolution future sans casser les widgets v2)
- **Clé attribut HPs** : `HP{1..4}_relStm`, `HP{1..4}_relEsp`, `HP{1..4}_relScr` (1 attribut par HP par champ)
- **Clé attribut générique** : dotted path joiné par underscore (`heat_calo_qeU`, `heat_slope`, etc.)

### Cas d'erreur

- **Payload mal formé** (`msg.HPs` présent mais clé manquante dans le script) : pas de crash, le script saute le champ via la garde `!= null`
- **Save Timeseries failure** : message envoyé sur output `Failure` de la rule chain, à diriger vers une queue/log dédiée (standard TB)
- **Attribut volumineux** (str_v > 255) : à surveiller via `SELECT max(length(str_v)) FROM attribute_kv WHERE entity_id IN (...)`

## 5. Mode live

### Mécanique

Un utilisateur ouvre le state `default` (Unité) ou `donnees_HP1` (Données détaillées PAC) du dashboard "Mes Installations". Le widget custom JS au mount :

1. Écrit `SHARED_SCOPE live=true` + `liveTs=Date.now()` via `ctx.attributeService.saveEntityAttributes()`
2. Démarre un setInterval 60 s qui rewrite `liveTs=Date.now()` tant que `document.visibilityState === 'visible'`
3. Au unmount / blur / visibilitychange→hidden / beforeunload : écrit `SHARED_SCOPE live=false`

### Côté firmware

À chaque cycle (cadence courante), avant le POST telemetry, le firmware fait :

```
GET /api/v1/{token}/attributes?sharedKeys=live
    → réponse JSON { "shared": { "live": true | false } }
```

- Si `shared.live === true` : cadence = 20 s
- Si `shared.live === false` ou absent : cadence = 60 s

### Sécurité timeout (côté TB)

Une nouvelle rule chain dédiée "Live Timeout Sweep" tourne en cron 1×/min :

```
[Generator node, originator=tenant, cron */1 * * * *]
    │
    ▼
[Fetch all PAC Hybride devices with attribute live=true]
    │
    ▼
[Filter : liveTs < (Date.now() - 180000)]   ← 3 min
    │
    ▼
[Save Attribute SHARED_SCOPE live=false]
```

Garantit que `live` retombe à false même si le client a fermé brutalement son browser sans déclencher `beforeunload`.

### Coût réseau

| Mode | POST telemetry | GET attributes | Total |
|---|---|---|---|
| Normal (1 client absent ou liveTs > 3 min) | 1/min | 1/min | 2 req/min |
| Live (1 client sur state default ou donnees_HP1) | 3/min (20 s) | 3/min | 6 req/min |

Le GET attributes a une réponse minuscule (~25 octets). Coût négligeable.

### Attributs SHARED_SCOPE introduits

- `live` (boolean) : flag mode live actif
- `liveTs` (long, epoch ms) : keep-alive du widget, MAJ toutes les 60 s

**Seuls** attributs SHARED_SCOPE du projet. Aucun setpoint en SHARED.

## 6. Migration : cutover par device via OTA

Pas de shadow write. La rule chain gère simultanément les deux formats (nested v2 et flat ancien) via le `Switch` sur `msg.HPs`. Chaque device flippe au gré de son OTA.

### Ordre de déploiement

| Jour | Action | Risque rollback |
|---|---|---|
| J0 | Deploy rule chain v2 (les 2 branches actives, aucun device en nested encore) | Revert rule chain version |
| J0 | Deploy widgets TDUO refactorisés sur dashboard | Revert dashboard json |
| J0 | Deploy rule chain "Live Timeout Sweep" (cron) | Désactiver le node |
| J0 | Setup cron PG `tb-ts_kv-drop-old-year.sh` (Section 8) | Désactiver le cron |
| J+1 | Pilot OTA sur 1 device test | Revert firmware sur ce device |
| J+1 | Validation : ligne `pac_v2` apparaît dans `ts_kv`, attributs présents dans `attribute_kv` | n/a |
| J+1 | Widget pilote sur le device test : Hub Info + Heating Loop + DHW + N×PAC affichent les bonnes valeurs | n/a |
| J+2 | Rollout OTA progressif (10% → 50% → 100% du parc) | Revert firmware lot par lot |
| J+7 | Cleanup device profile : suppression des 13 alarms orphelines | Recréer les alarms si besoin |

### Critères de validation au pilote (J+1)

```sql
-- 1. Ligne pac_v2 présente sur le device pilote
SELECT key, value_json
FROM ts_kv
WHERE entity_id = '<uuid pilote>'
  AND key = (SELECT key_id FROM ts_kv_dictionary WHERE key = 'pac_v2')
ORDER BY ts DESC LIMIT 1;

-- 2. Attributs présents
SELECT key_id, str_v, long_v, dbl_v, bool_v
FROM attribute_kv
WHERE entity_id = '<uuid pilote>'
  AND attribute_type = 'SERVER_SCOPE';

-- 3. Plus aucune ligne flat depuis le cutover sur ce device
SELECT count(*) FROM ts_kv
WHERE entity_id = '<uuid pilote>'
  AND ts > <ts_cutover>
  AND key != (SELECT key_id FROM ts_kv_dictionary WHERE key = 'pac_v2')
  AND key NOT IN (SELECT key_id FROM ts_kv_dictionary WHERE key LIKE 'evt_%');
-- attendu : 0
```

### Rollback par device

Un device peut être rebasculé en firmware ancien (flat) à tout moment : la branche `Switch=false` de la rule chain l'accepte. Aucun nettoyage requis côté TB.

## 7. Refonte dashboard "Mes Installations"

8 états identifiés sur le dashboard. Plan d'action par état :

| State ID | Nom affiché | Root | Action |
|---|---|---|---|
| `menu` | Menu | **true** | Pas de changement obligatoire ; optionnel : tile résumé TDUO Tile en mode "summary" si utile |
| `default` | Unité | false | **Refonte complète** : Hub Info + Heating Loop Card + DHW Card + N × PAC Synoptic + Boiler Synoptic (conditionnel sur présence chaudière) — déclenche mode live |
| `donnees_HP1` | Données détaillées PAC | false | **Refonte** : 1 × PAC Synoptic en pleine page (lit `pac_v2.HPs[selected].*`) — déclenche mode live |
| `configuration` | Configuration | false | Hors scope payload v2 (saisie user/account, pas device setpoint) |
| `fault_diagnostic` | Diagnostic défaut | false | **Intouché** (lit `evt_*` qui reste flat) |
| `historique` | Historique | false | **Refonte** : Chart.js custom lisant array `pac_v2` sur fenêtre temporelle, avec extraction côté JS de `pac_v2.heat.tOut`, etc. |
| `profil` | Mon profil | false | **Intouché** |
| `notifications_admin` | Notifications (admin) | false | **Intouché** (iframe externe) |

### Les 6 widgets TDUO (refactor)

Bundle `tduo.*` déjà créé (2026-04-22), aucun deprecated, tailles 5-9 KB. Refactor = changer les datasources pour lire `pac_v2` au lieu de flat.

| Widget | fqn | Lecture v2 | Placement |
|---|---|---|---|
| Hub Info | `tduo.hub_info` | `pac_v2.tExt`, `pac_v2.press`, attributs `id`, `rel`, `modType` | `default` (haut de page) |
| Heating Loop Card | `tduo.heating_loop_card` | `pac_v2.heat.tOut/tIn/posV3V/qeCalc/calo.*` | `default` |
| DHW Card | `tduo.dhw_card` | `pac_v2.dhw.tOut/tIn/tTank/posV3V/pump1..4` | `default` |
| PAC Synoptic | `tduo.pac_synoptic` | `pac_v2.HPs[i].HP/invert/pump` | `default` (×N) et `donnees_HP1` (×1 plein écran) |
| Boiler Synoptic | `tduo.boiler_synoptic` | `pac_v2.HPs[i].boil.*` | `default` (conditionnel sur `boil.status` != null) |
| TDUO Tile | `tduo.tduo_tile` | template / brique de base | n/a directement, sert d'inclusion aux 5 autres |

### Composants à supprimer / archiver

- 12 widgets `markdown_card` actuels du dashboard `Mes Installations` (états `default` et probablement `donnees_HP1`) — remplacés par les TDUO
- `usage_pie` (custom JS) si lit du flat — à adapter ou supprimer
- 13 alarms orphelines du device profile PAC Hybride : `HPxFault` ×4, `BoilxFault` ×4, `SensorxFault` ×4, `Offline` ×1

## 8. Rotation stockage : 3 ans glissants + année en cours

### Politique

À tout moment, `ts_kv` contient :

- L'année en cours (partielle ou complète)
- Les 3 dernières années complètes (du 1er janvier au 31 décembre)

Au 1er janvier de chaque année N, on supprime toutes les partitions de l'année N-4.

### Implémentation

Script bash + cron annuel sur le serveur prod (`root@10.77.0.74`) :

**`/usr/local/bin/tb-ts_kv-drop-old-year.sh`**

```bash
#!/bin/bash
# Drop ts_kv partitions older than 3 full years + current year.
# Run yearly on Jan 1st 02:00.

set -euo pipefail

YEAR_TO_DROP=$(( $(date +%Y) - 4 ))
LOG="/var/log/tb-ts_kv-drop.log"

echo "$(date -Iseconds) — dropping ts_kv partitions for year ${YEAR_TO_DROP}" >> "${LOG}"

for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  PARTITION="ts_kv_${YEAR_TO_DROP}_${m}"
  sudo -u postgres psql thingsboard -c "DROP TABLE IF EXISTS ${PARTITION};" \
    >> "${LOG}" 2>&1 || echo "FAIL on ${PARTITION}" >> "${LOG}"
done

echo "$(date -Iseconds) — done" >> "${LOG}"
```

**`/etc/cron.d/tb-storage-rotation`**

```cron
# m h dom mon dow user command
0 2 1 1 * root /usr/local/bin/tb-ts_kv-drop-old-year.sh
```

### Config TB

- Default Storage TTL du device profile **PAC Hybride** : `0` (illimité) — c'est le script PG qui gère la rotation, pas le worker TB.

### Volume attendu (post-migration)

| Parc | Cadence | Payload | Lignes/an/device | Bytes/an/device | Bytes/an total (4 ans gardés) |
|---|---|---|---|---|---|
| 3 PACs (actuel) | 1/min | ~3.2 KB | 525 600 | ~1.7 GB | **~20 GB** |
| 30 PACs (cible court terme) | 1/min | ~3.2 KB | 525 600 | ~1.7 GB | ~200 GB |
| 60 PACs (cible long terme) | 1/min | ~3.2 KB | 525 600 | ~1.7 GB | ~400 GB |

Pour 60 PACs il faudra envisager le SBS resize Scaleway (voir [project-thingsboard-storage-optim]).

## 9. Exigences firmware

### F1 — Endpoint et format

POST `https://thingsboard.tsmart.fr/api/v1/{token}/telemetry`
Content-Type: `application/json`
Body : JSON conforme Section 3, non pretty-printed

### F2 — Cadence

- **Mode normal** : 1 POST / 60 s
- **Mode live** : 1 POST / 20 s
- Cadence est lue à chaque cycle via GET attributes (F6)

### F3 — Format `dateTime`

String `"JJ/MM/AA HH:MM:SS"` formatée par RTC local. Pas d'offset timezone.

### F4 — Bloc HPs

`HPs` est un array, longueur = nombre de HP physiquement présents (max 4). Pas d'élément placeholder. Si 0 HP, array vide.

### F5 — Blocs `heat` et `dhw`

Toujours présents dans le JSON. Valeurs à `0` si non applicables au modType (typiquement pas de bloc absent).

### F6 — GET attributes pour mode live

À chaque cycle (juste avant le POST telemetry) :

```
GET /api/v1/{token}/attributes?sharedKeys=live
```

Si `shared.live === true` : adapter la cadence à 20 s pour le prochain cycle.
Si `shared.live === false`, absent, ou erreur réseau : cadence 60 s par défaut.

### F7 — Encodage

- UTF-8 sans BOM
- Floats max 1 décimale (sauf strings de version `"1.04"`)
- Booléens : integer `0` / `1`
- Pas de retours ligne dans le JSON
- Content-Length set correctement

### F8 — Buffer offline et retry

- Sur perte WAN : buffer N samples en RAM/FRAM (N à dimensionner selon taille buffer ; ~3 KB par sample)
- Reconnexion : POST chaque sample en séquence, TB déduplique sur le `ts` interne
- Retry max 3 fois avec backoff `5, 15, 60` s, puis abandon ce sample

### F9 — Compatibilité firmware ancien

Pendant la phase de rollout, certains devices continueront d'envoyer le format flat ancien. La rule chain TB l'accepte sans modification (branche `Switch=false`). Aucune coordination firmware ⇄ TB nécessaire au déploiement.

### F10 — Modification setpoints

**Hors scope payload v2.** Les consignes sont modifiées par voie locale (écran physique, LAN, BLE). Le firmware remonte les setpoints courants dans le payload via les champs `[ATTR]`. TB **n'est jamais source de vérité** pour les setpoints.

## 10. Inventaire composants

### À modifier

| Composant | Type | Action |
|---|---|---|
| Rule chain "PAC Hybride Router" | TB rule chain | **Remplacer** (Section 4) |
| Rule chain "Live Timeout Sweep" | TB rule chain | **Créer** (Section 5) |
| Device profile "PAC Hybride" : default rule chain | TB device profile | Pointer vers "PAC Hybride Router v2" |
| Device profile "PAC Hybride" : alarms | TB device profile | Supprimer les 13 orphelines |
| Device profile "PAC Hybride" : default storage TTL | TB device profile | Mettre à 0 (illimité) |
| Dashboard "Mes Installations" : state `default` | TB dashboard | Refonte widgets : Hub Info + Heating Loop + DHW + N×PAC + Boiler |
| Dashboard "Mes Installations" : state `donnees_HP1` | TB dashboard | 1 × PAC Synoptic plein écran |
| Dashboard "Mes Installations" : state `historique` | TB dashboard | Charts Chart.js lisant array `pac_v2` |
| Widget bundle `tduo.*` (6 widgets) | TB widget | **Refactor** : datasources sur `pac_v2.*` |
| Widget `usage_pie` (custom JS) | TB widget | Refactor si lit du flat, sinon supprimer |
| Server-side script `/usr/local/bin/tb-ts_kv-drop-old-year.sh` | Bash | **Créer** (Section 8) |
| Cron `/etc/cron.d/tb-storage-rotation` | cron | **Créer** (Section 8) |
| Firmware (repo séparé) | Code embedded | **Refonte** (Section 9) |

### Intouchés

| Composant | Raison |
|---|---|
| Widget `events_history` | Lit `evt_*` qui reste flat |
| Widget `fault_diagnostic` | Idem |
| Widget `system.map` | Lit attribut `location` indépendant |
| Iframes `notifications_admin` | Indépendant, lien externe |
| Pipeline `tb-notify` | Indépendant, déclenche sur evt_* |
| Rule chain "Root Rule Chain" | Indépendante de "PAC Hybride Router" |
| Branche `Switch=false` de "PAC Hybride Router v2" | Préserve le routage flat pour devices anciens et POST `evt_*` séparés |

## 11. Décisions différées

Hors scope de cette spec, à trancher au moment où le palier se pose :

- **TimescaleDB (levier C1 de la mémoire)** : à activer si volume devient ingérable. Continuous aggregates supplantent la pré-agg manuelle.
- **Pré-agrégation horaire** : à activer si les charts du state `historique` deviennent lents (> 3 s sur 6 mois). Trois options : TimescaleDB continuous aggregate, rule chain Time Window Aggregator node, ou cron PostgreSQL custom.
- **Nouvelles alarmes** sur le payload v2 : ex `pac_v2.HPs[*].HP.status` en code erreur, `pac_v2.press` hors plage, "Offline" basée sur absence de POST > 5×cadence courante. À spécifier après cutover.
- **Migration cleanup historique flat** : à T+1 an du cutover, décider si on DROP les partitions `ts_kv_2026_*` antérieures au cutover (libère ~50% du volume actuel) ou si on les garde pour comparaisons.
- **6e TDUO `TDUO Tile`** : usage exact à déterminer (probablement template inclus par les 5 autres, à confirmer en lisant le descriptor).

## 12. Risques et mitigations

| Risque | Détection | Mitigation |
|---|---|---|
| Script TBEL crash sur 1 post | Failure queue rule chain | Sortie défaut → drop sample (=1 min de données perdues max) |
| Widget TDUO refactorisé affiche valeurs incohérentes | Visuel dashboard pilote J+1 | Revert widget bundle vers version précédente ; la donnée `pac_v2` reste écrite |
| Firmware nested mal formé en production | Switch détecte HPs mais script échoue ; alarme TB sur Failure queue | OTA revert au firmware précédent sur ce device ; branche flat compat prend le relais automatiquement |
| Attribute_kv str_v > limite | `SELECT max(length(str_v))` régulièrement | Réduire ATTR_PATHS dans le script TBEL, redéployer rule chain à chaud |
| Live Timeout Sweep manque de tourner | Devices restent en cadence 20 s sans client | Surveillance via log de la rule chain ; option (c) firmware-side check `liveTs` < 3 min comme ceinture+bretelles |
| Cron DROP PARTITION échoue (verrou, espace) | `/var/log/tb-ts_kv-drop.log` | Alerte log + tentative manuelle ; impact = on garde 1 année de plus, pas critique |

## 13. Acceptance criteria

Le projet est considéré terminé quand :

- 100% des devices PAC Hybride du parc envoient en format nested v2 (vérifiable via `SELECT count(*) FROM ts_kv WHERE key = 'pac_v2' GROUP BY entity_id`)
- Aucune ligne `ts_kv` flat n'est plus écrite (hors `evt_*`) après J+30 du dernier OTA
- Les attributs SERVER_SCOPE sont présents sur chaque device : 5 (métadonnées root) + 9 (consignes heat) + 1 (dhw.tSet) + 5 (unités calo) + 3×N (versions par HP, N = nb HPs présents). Min 20 pour 0 HP, max 32 pour 4 HPs
- Le state `default` et `donnees_HP1` affichent correctement les valeurs depuis `pac_v2` sur les 6 widgets TDUO refactorisés
- Le mode live est observable : cadence passe à 20 s quand un client ouvre `default` ou `donnees_HP1`, retombe à 60 s 3 min après la fermeture
- Le state `historique` affiche un chart 1 an en < 3 s
- Le script de rotation `tb-ts_kv-drop-old-year.sh` a été testé sur un mois fictif (création + drop manuel d'un partition de test)
- Les 13 alarmes orphelines sont supprimées du device profile

# Payload v2 PAC Hybride — Design

**Date** : 2026-05-28
**Auteurs** : Julien (product), Claude (design)
**Statut** : Brouillon, en attente de validation utilisateur avant plan d'implémentation
**Branche** : `yahtec-main`

## 1. Contexte

### Architecture cible

```
[Firmware PAC]  ──Modbus──►  [Automate]  ──HTTPS──►  [Proxy / buffer]  ──HTTPS──►  [ThingsBoard]
                                                            │
                                                            └─ Buffer local si TB indisponible
                                                               (rejoue les POSTs avec leur ts d'origine
                                                                à la reconnexion)
```

Trois couches distinctes :

- **Firmware PAC** : acquisition métier, expose ses données en Modbus local. Ne parle pas HTTP.
- **Automate** : composant logique qui agrège les données Modbus, construit le JSON nested v2 (Section 3), ajoute `ts` (epoch ms d'acquisition), et POSTe vers le proxy. C'est le **générateur du payload**.
- **Proxy / buffer** : passthrough transparent entre l'automate et TB. Il forwarde la requête HTTP **sans la modifier** (même URL, même body, même query string, mêmes headers). Si TB est injoignable, le proxy bufferise la requête et la rejoue ultérieurement avec le `ts` que l'automate a déjà mis dans le body. Au retour, le proxy relaie la réponse TB telle quelle à l'automate.

Le `ts` est fixé **par l'automate au moment de l'acquisition**, jamais par le proxy. Le proxy n'a pas à comprendre la sémantique du payload.

Le proxy peut aussi répondre à l'automate sur la base d'un cache local (ex : 200 OK ack même si TB est temporairement down, pour que l'automate ne retente pas inutilement) ; le contrat exact proxy ↔ automate est détaillé en Section 9.5.

### Mesures historiques

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

L'automate POSTe vers le proxy ; le proxy forwarde à TB sans modification d'URL :

```
POST <proxy_host>/api/v1/{deviceAccessToken}/telemetry
Content-Type: application/json
```

**Pas de query param spécial sur TB.** Le proxy gère `live` lui-même (Section 9.2) et l'injecte dans la réponse retournée à l'automate. Pour TB, c'est une requête `POST /telemetry` standard.

Le body est wrappé pour permettre l'envoi d'un `ts` explicite (essentiel pour le rejeu après buffer) :

```json
{
  "ts": 1716902040000,
  "values": {
    "dateTime": "20/01/26 16:34:00",
    "id": "2503200123",
    "...": "structure nested ci-dessous"
  }
}
```

- `ts` : epoch ms du moment de l'acquisition côté firmware/automate (pas le moment de l'envoi à TB). Permet à TB d'attribuer le bon timestamp même quand l'automate rejoue des samples bufferisés.
- `values` : le payload nested complet décrit ci-dessous.

Pas de pretty-print. Body UTF-8.

### Structure nested (`values`)

```yaml
Chaufferie:
  dateTime: "20/01/26 16:34:00"   # JJ/MM/AA HH:MM:SS (24h, slash, espace, deux-points)
  id:        "2503200123"         # [ATTR] série device
  rel:       "1.04"               # [ATTR] version programme CPU principal
  modType:   3                     # [ATTR] enum 0..3
                                   #   0 = no module, 1 = heating, 2 = dhw, 3 = heating + dhw
  nHp:       2                     # [ATTR] nombre de HPs réellement présents (1..4)
                                   #   HPs[] est toujours de longueur 4, les indices >= nHp ont des slots à 0 / "" / "0.00"
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
    pwr: 0
    dP: 0
    qe: 0
    rpm: 0
    time: 4000

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

  HPs:                              # array de longueur FIXE = 4. Les indices >= nHp sont des slots "vides"
                                    # (numerics à 0, strings de version à "", autres strings à "0.00" si applicable).
                                    # Avantages : pas de gestion d'array dynamique côté automate, parsing widget simplifié.
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
| Métadonnées (id, rel, modType, nHp, commCm2, relCm2) | 6 | au root |
| Consignes heat (slope, foot, tMax, jours/mois été ×4, tCut, tRes) | 9 | sous `heat` |
| Consigne dhw (tSet) | 1 | sous `dhw` |
| Unités calo (qeU, qeTotU, pwrU, hKwhU, cKwhU) | 5 | sous `heat.calo` |
| Versions par HP (relStm, relEsp, relScr) × 4 HPs (fixe) | 12 | sous `HPs[].` |
| **Total** | **33** | constant quel que soit le nb de HPs réellement actifs |

### Modifications vs schéma initial

| Changement | Avant | Après |
|---|---|---|
| Date+heure | 2 strings `date` + `time` | 1 string combiné `dateTime` |
| Type module (root) | `type` (mot réservé dans certains langages/gen OpenAPI) | `modType` |
| Nombre HP | `nHp` explicite | **gardé** ; HPs[] toujours de longueur 4, slots inutilisés à 0 |
| Vanne expansion | `dpf` (peu clair) | `eevPos` |
| Wrapper TB | body direct | `{ "ts": ..., "values": { ... } }` (permet rejeu après buffer du proxy) |
| Routing | tout en ts_kv flat | nested, rule chain extrait 33 paths en SERVER_SCOPE |
| Réponse POST | 200 body vide | 200 avec body `{ "shared": { "live": <bool> } }` injecté par le proxy |

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
// Paths à router en SERVER_SCOPE. Préfixe HPs.* applique sur chaque élément de l'array (longueur fixe 4).
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

### Côté automate

L'automate lit `live` **dans la réponse de son POST telemetry au proxy**. Le proxy a forwardé la requête à TB (sans rien de spécial) puis a injecté `live` dans la réponse à partir de sa connaissance locale :

```
POST <proxy_host>/api/v1/{token}/telemetry
  body : { "ts": <ms>, "values": { ... payload v2 ... } }
  → 200 OK
  → response body : { "shared": { "live": true | false } }
```

- Si `shared.live === true` : cadence = 20 s
- Si `shared.live === false`, absent, ou body de réponse vide : cadence = 60 s

Le proxy maintient sa connaissance de `live` via un canal séparé vers TB (Section 9.2 P7). L'automate ne voit jamais la mécanique de discovery.

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

Côté **automate ↔ proxy** :

| Mode | POSTs/min | Notes |
|---|---|---|
| Normal | 1 | réponse proxy contient `{"shared":{"live":false}}` |
| Live | 3 (cadence 20 s) | réponse proxy contient `{"shared":{"live":true}}` |

Côté **proxy ↔ TB** (option P7-a) : pour chaque POST forwardé, 1 GET attributes en parallèle. Soit 2× le trafic vers TB par rapport au seul POST. Reste sur le canal cloud, ne touche pas le LAN automate.

### Attributs SHARED_SCOPE introduits

- `live` (boolean) : flag mode live actif
- `liveTs` (long, epoch ms) : keep-alive du widget, MAJ toutes les 60 s

**Seuls** attributs SHARED_SCOPE du projet. Aucun setpoint en SHARED.

## 6. Migration : proxy d'abord, puis cutover payload v2 par device via OTA

### Phasage

Deux phases distinctes :

**Phase 0 — Proxy** (avant tout autre changement). Mise en place du proxy en mode pur passthrough pour le **format flat actuel**. À la fin de la phase, tous les devices passent par le proxy mais envoient toujours du flat ; TB reçoit exactement la même chose qu'aujourd'hui. Le proxy n'a pas encore besoin de gérer `live` puisque le firmware actuel ne fait pas de mode live.

**Phase 1+ — Payload v2** (rule chain + widgets + automate v2). Une fois Phase 0 stable, on déploie tout le reste (Sections 3-5, 7, 8). Le proxy se met à gérer `live` quand le premier automate v2 entre en service.

### Phase 0 — Proxy

| Étape | Action | Validation |
|---|---|---|
| P0.1 | Développer le proxy (P1-P5, passthrough + buffer). P6/P7 (live discovery) peuvent être stubés : retourner toujours `{"shared":{"live":false}}` | Tests unitaires proxy |
| P0.2 | Déployer le proxy sur infra cible (mini-PC LAN, raspberry, container cloud — TBD selon archi) | Health check proxy OK |
| P0.3 | Reconfigurer 1 device pilote pour pointer vers `<proxy_host>` au lieu de TB direct | Lignes `ts_kv` arrivent toujours (format flat) sur ce device dans TB |
| P0.4 | Tester scénario buffer : couper TB ~5 min, vérifier que les POST sont bufferisés côté proxy puis rejoués à la reconnexion | Lignes `ts_kv` apparaissent avec `ts` d'origine |
| P0.5 | Rollout reconfiguration sur tous les devices du parc | Volume `ts_kv` quotidien inchangé vs avant proxy |
| P0.6 | Activer P6/P7 (live discovery) dans le code proxy. Pas d'impact tant que les automates v2 n'existent pas. | GET attributes proxy→TB fonctionnel |

### Phase 1+ — Cutover payload v2 (par device via OTA)

Pas de shadow write. La rule chain gère simultanément les deux formats (nested v2 et flat ancien) via le `Switch` sur `msg.HPs`. Chaque device flippe au gré de son OTA. Tous les devices passent déjà par le proxy depuis Phase 0.

| Jour | Action | Risque rollback |
|---|---|---|
| J0 | Deploy rule chain v2 (les 2 branches actives, aucun device en nested encore) | Revert rule chain version |
| J0 | Deploy widgets TDUO refactorisés sur dashboard | Revert dashboard json |
| J0 | Deploy rule chain "Live Timeout Sweep" (cron) | Désactiver le node |
| J0 | Setup cron PG `tb-ts_kv-drop-old-year.sh` (Section 8) | Désactiver le cron |
| J+1 | Pilot OTA automate v2 sur 1 device test | Revert firmware sur ce device |
| J+1 | Validation : ligne `pac_v2` apparaît dans `ts_kv`, attributs présents dans `attribute_kv`, proxy retourne `live` correctement | n/a |
| J+1 | Widget pilote sur le device test : Hub Info + Heating Loop + DHW + N×PAC affichent les bonnes valeurs ; ouverture du state `default` fait passer la cadence à 20 s | n/a |
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

## 9. Exigences automate + proxy

### 9.1 Automate (générateur du payload)

L'automate agrège les données firmware (Modbus local) et POSTe vers le proxy. Du point de vue de l'automate, le proxy se comporte comme TB ; il n'y a aucun ajustement à faire dans le code automate du fait du proxy.

#### M1 — Endpoint et format

```
POST https://<proxy_host>/api/v1/{token}/telemetry
Content-Type: application/json
```

`<proxy_host>` est l'adresse du proxy (LAN local typiquement). Le proxy forwarde vers `thingsboard.tsmart.fr` sans modification d'URL. Pas de query param spécial : le proxy injecte `live` dans la réponse à partir de sa propre connaissance.

Body : objet wrappé avec `ts` explicite :

```json
{ "ts": 1716902040000, "values": { "...nested payload v2..." } }
```

#### M2 — Cadence

- **Mode normal** : 1 POST / 60 s
- **Mode live** : 1 POST / 20 s
- Cadence ajustée à chaque cycle à partir du `shared.live` lu dans la réponse du POST précédent

#### M3 — Format `dateTime`

Field `values.dateTime` = string `"JJ/MM/AA HH:MM:SS"` formatée à partir du RTC local de l'automate ou du firmware (24h, slash, espace, deux-points, année sur 2 chiffres). Pas d'offset timezone.

Construction typique en C :
```c
char dateTime[20];
sprintf(dateTime, "%02d/%02d/%02d %02d:%02d:%02d",
        rtc.day, rtc.month, rtc.year % 100,
        rtc.hour, rtc.minute, rtc.second);
```

#### M4 — Bloc HPs : longueur fixe 4

`values.HPs` est **toujours un array de longueur 4**. `values.nHp` indique combien sont réellement actifs. Les indices `[nHp .. 3]` doivent contenir des slots avec valeurs neutres :

- numérics → `0`
- strings de version → `""` (chaîne vide)
- autres strings → `"0.00"` ou similaire selon convention firmware

Avantage : pas de gestion d'array dynamique côté automate, parsing trivial côté widget.

#### M5 — Blocs `heat` et `dhw`

Toujours présents dans le JSON. Valeurs à `0` si non applicables au `modType`.

#### M6 — Mode live : depuis la réponse du proxy

À chaque POST telemetry, l'automate lit le body de réponse retourné par le proxy :

```json
{ "shared": { "live": true | false } }
```

- `live === true` → cadence prochain POST = 20 s
- `live === false`, absent, body vide, ou erreur réseau → cadence 60 s par défaut

Le proxy est responsable du maintien de `live`. L'automate ne fait jamais d'appel séparé à TB pour ça.

#### M7 — Encodage

- UTF-8 sans BOM
- Floats max 1 décimale (sauf strings de version `"1.04"`)
- Booléens : integer `0` / `1`
- Pas de retours ligne dans le JSON
- Content-Length set correctement

#### M8 — Retry réseau côté automate

Le buffer offline est **délégué au proxy** (Section 9.2). L'automate fait du retry simple côté HTTP :

- Sur timeout / erreur 5xx du proxy : max 3 retries avec backoff `5, 15, 60` s
- Au-delà : abandon de ce sample (le proxy est censé absorber les pannes TB ; un échec persistant proxy → automate est probablement un problème de LAN à investiguer)

L'automate n'a pas besoin de bufferiser lui-même : le proxy le fait pour TB.

#### M9 — Compatibilité firmware ancien

Pendant la phase de rollout, certains devices ne sont pas encore reliés à l'automate middleware et POSTent directement en format flat ancien. La rule chain TB accepte les deux formats (Section 4) sans coordination supplémentaire.

#### M10 — Modification setpoints

**Hors scope payload v2.** Les consignes sont modifiées par voie locale (écran physique du firmware, LAN, BLE). Le firmware remonte les setpoints courants à l'automate via Modbus ; l'automate les remonte dans le payload via les champs `[ATTR]`. TB **n'est jamais source de vérité** pour les setpoints.

### 9.2 Proxy / buffer

Composant intercalé entre l'automate et TB. Rôle unique : **passthrough HTTP avec buffer persistant**.

#### P1 — Transparence

Le proxy ne modifie **jamais** :
- L'URL forwardée (path, query string)
- Les headers significatifs (`Content-Type`, `Content-Length`, auth si applicable)
- Le body de la requête
- Le body et le status code de la réponse

Du point de vue de l'automate : `<proxy_host>` est interchangeable avec `thingsboard.tsmart.fr`. Du point de vue de TB : la requête est indiscernable d'une requête directe de l'automate (sauf adresse IP source = proxy).

#### P2 — Forwarding nominal

Quand TB est joignable :
1. Receive POST de l'automate
2. Forward HTTPS à TB avec le même body/URL/headers
3. Receive response TB (typiquement 200 + body `{"shared":{"live":...}}` ou 200 vide)
4. Forward response à l'automate

Latence ajoutée : 1 hop TCP + parse/forward (~ms en LAN, ~10 ms en WAN).

#### P3 — Comportement buffering

Quand TB est injoignable (timeout, 5xx, erreur DNS, etc.) :
1. Receive POST de l'automate
2. **Persister** la requête (méthode + URL + headers + body) sur disque local du proxy
3. Répondre 200 OK à l'automate avec un body neutre (ex : `{"shared":{"live":false}}`) — par défaut mode normal côté automate
4. En tâche de fond, retenter le forward vers TB avec backoff exponentiel (60 s, 120 s, 240 s, max 600 s)
5. À la reconnexion TB : rejouer les requêtes bufferisées dans l'ordre FIFO, avec leur body d'origine (le `ts` interne au JSON est préservé → TB attribue la bonne ligne `ts_kv`)
6. Si une requête rejouée échoue (TB répond 4xx — payload invalide par exemple) : log et drop, ne bloque pas la file

#### P4 — Capacité buffer

Minimum recommandé : **24 h de samples** = 1 440 × ~3 KB = ~5 MB. Le proxy est typiquement sur un mini-PC LAN ou un raspberry, donc dimensionnable beaucoup plus large (Go disponibles). Politique d'éviction si plein : FIFO drop des plus anciens.

#### P5 — Idempotence et déduplication

TB **n'a pas** de mécanisme natif de déduplication sur `ts`. Si le proxy rejoue 2× la même requête (ex : redémarrage du proxy avec un sample partiellement persisté), TB écrira **2 lignes** dans `ts_kv` avec le même `ts`. Conséquence : valeur dupliquée dans les charts.

Mitigation : le proxy maintient un compteur de séquence ou un hash du body pour éviter le re-POST d'une même requête au sein d'une session. Détail d'implémentation, hors spec.

#### P6 — Réponse `shared.live` quand TB est down

Pendant un buffering, le proxy ne connaît pas la valeur réelle de `live` côté TB. Politique par défaut : répondre `{"shared":{"live":false}}` → l'automate reste en cadence 60 s (mode normal) tant que la connexion TB n'est pas rétablie. Garde le buffer plus contenu (60 s de cycle au lieu de 20 s).

#### P7 — Discovery de `live` côté TB

Le proxy maintient en mémoire, par device qu'il sert, la valeur courante de `shared.live`. Stratégies, par ordre de préférence :

**(a) GET attributes piggyback sur chaque POST** : à chaque POST de l'automate qui est forwardé avec succès à TB, le proxy fire **en parallèle** un `GET /api/v1/{token}/attributes?sharedKeys=live` vers TB et stocke le résultat dans son cache local. La réponse au POST est constituée à partir de ce cache (valeur précédente). Latence = 0 pour l'automate (la réponse retourne quand TB répond au POST). Coût : double les requêtes proxy → TB (mais reste sur le canal cloud, l'automate ne le voit pas).

```
Automate POST ─► Proxy ─┬─► TB (POST telemetry)
                        └─► TB (GET attributes?sharedKeys=live)  ─► cache[token].live
Proxy ─► Automate { "shared": { "live": cache[token].live } }
```

**(b) Polling périodique** : le proxy fait un GET attributes toutes les N secondes (ex : 30 s) en arrière-plan, indépendamment des POSTs. Plus simple ; latence de propagation jusqu'à N secondes.

**(c) WebSocket subscription** : le proxy ouvre une WS vers TB et s'abonne aux mises à jour d'attributs SHARED pour les devices servis. Push instantané. Plus complexe (gestion de la reconnexion WS), mais le plus efficace pour beaucoup de devices.

**Recommandation** : option (a) pour la v1 du proxy — simple, sans timer séparé, propagation immédiate au prochain POST. Migration vers (c) si volume devient un problème.

Au démarrage froid (cache vide) : `cache[token].live = false` par défaut, premier GET au prochain POST initialise.

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
| Automate (générateur payload v2) | Code automate, repo séparé | **Développer** (Section 9.1, M1-M10) |
| Proxy / buffer | Code séparé (mini-PC LAN, raspberry, ou container) | **Développer** (Section 9.2, P1-P7) |
| Firmware PAC | Code embedded, repo séparé | **Inchangé** côté HTTP (parle uniquement Modbus à l'automate maintenant) |

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
- **Extension TB `postTelemetry?withSharedKeys=live`** : initialement prévue (patch sur `DeviceApiController.java` côté fork yahtec) pour éviter au client un GET attributes séparé. Décision actuelle : c'est le **proxy** qui gère cette injection (Section 9.2 P7), pas TB. Avantage : aucune modification de code TB, pas de risque de conflit merge LTS. Inconvénient : 1 GET attributes supplémentaire proxy→TB par POST. Si la charge cloud devient problématique, réintroduire l'extension TB devient une option (le code design reste valable, archivé dans l'historique git de cette spec).

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
- Les 33 attributs SERVER_SCOPE sont présents sur chaque device : 6 (métadonnées root, incluant nHp) + 9 (consignes heat) + 1 (dhw.tSet) + 5 (unités calo) + 12 (versions par HP × 4 fixe)
- Le proxy retourne dans la réponse à l'automate `{"shared":{"live":<bool>}}` reflétant l'état courant en TB ; pendant une indisponibilité TB, retourne `{"shared":{"live":false}}` (mode normal)
- L'automate POSTe avec `ts` explicite vers le proxy ; les samples rejoués par le proxy après reconnexion TB apparaissent dans `ts_kv` à leur `ts` d'origine et non au timestamp de réception
- Le state `default` et `donnees_HP1` affichent correctement les valeurs depuis `pac_v2` sur les 6 widgets TDUO refactorisés
- Le mode live est observable : cadence passe à 20 s quand un client ouvre `default` ou `donnees_HP1`, retombe à 60 s 3 min après la fermeture
- Le state `historique` affiche un chart 1 an en < 3 s
- Le script de rotation `tb-ts_kv-drop-old-year.sh` a été testé sur un mois fictif (création + drop manuel d'un partition de test)
- Les 13 alarmes orphelines sont supprimées du device profile

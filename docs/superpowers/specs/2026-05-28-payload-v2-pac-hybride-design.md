# Payload v2 PAC Hybride — Design

**Date** : 2026-05-28
**Auteurs** : Julien (product), Claude (design)
**Statut** : Phase 0 (proxy) **VALIDÉE en prod 2026-05-28** ; Phases 1+ (rule chain v2, widgets, dashboard) à dérouler
**Branche** : `yahtec-main`

## Statut d'implémentation

| Phase | Statut | Date |
|---|---|---|
| 0 — Proxy mode v2 (parse `dateTime` + wrap `{ts, values}` + cache offline) | ✅ DONE | 2026-05-28 |
| 1+ — Payload nested v2, rule chain TBEL, widgets TDUO, dashboard, rotation | À dérouler | — |

### Validation Phase 0 (résumé)

- Proxy Rust `telemetry-proxy 0.1.0` déployé sur `10.77.0.74`, service systemd, toggle `tb_format` activable via UI admin (`https://bootloader.tsmart.fr/proxy/ui`)
- Test rupture TB 5 min (2026-05-28 16:55-17:00 UTC) :
  - Cache passé 0 → 11 entrées pendant la panne
  - Replay automatique à la reconnexion, cache vidé en ~60 s
  - Les 2 vrais devices PAC (`2602000001`, `2602000002`) ont reçu **5 samples × ~247 keys** chacun pendant la panne, ts d'acquisition d'origine préservé
- Mémoire détaillée : [[project-proxy-pac-hybride]]

### Architecture réelle découverte (vs initialement spec)

Le proxy POSTe via **un seul token TB** (`yDq5GxcbQpuJVgKYRiWu` → device `heatPumpHybride` profile `default`). Ce device joue le rôle de **dispatcher** : une rule chain TB lit l'`installation_id` du body et **redispatche** la télémétrie vers le vrai device PAC correspondant (profile `pac hybride`). C'est ce mécanisme qui assure la séparation par installation (2602000001, 2602000002, 2610000001, ...) sans démultiplier les configs proxy.

Pour la migration v2 (Phases 1+), la rule chain TBEL split-attributes-from-payload devra tourner **sur les vrais devices PAC** (en sortie du dispatcher), pas sur le dispatcher lui-même.

## 1. Contexte

### Architecture cible

```
[Firmware PAC]   ──Modbus──►  [Automate]   ──HTTPS 1/min──►  [Proxy /tduo]   ──HTTPS──►  [TB device dispatcher
 (2602000001/2/...)              tb_format=true                                            heatPumpHybride
                                 parse dateTime                                            profile default]
                                 wrap {ts, values}                                                │
                                 cache offline                                                    ▼ rule chain
                                                                                          lit installation_id
                                                                                                  │
                                                                                                  ├─► evt_dispatch
                                                                                                  │   (trace sur dispatcher)
                                                                                                  └─► redispatch payload
                                                                                                      vers vrai device PAC
                                                                                                      (profile "pac hybride") :
                                                                                                        2602000001
                                                                                                        2602000002
                                                                                                        2610000001
                                                                                                        ...
```

Quatre couches distinctes :

- **Firmware PAC** : acquisition métier, expose ses données en Modbus local. Ne parle pas HTTP.
- **Automate** : agrège Modbus, construit le JSON nested v2 (Section 3) **avec un champ `dateTime` string** (`"dd/MM/yy HH:mm:ss"` UTC, formaté depuis le RTC). POSTe vers le proxy à cadence **1 POST/min fixe**. L'automate **ne calcule pas** d'epoch ms — il envoie juste la string.
- **Proxy** (`telemetry-proxy` 0.1.0 Rust, déjà déployé) : parse `dateTime` UTC en epoch ms et enveloppe en `{ts, values}` avant forward à TB. Le `ts` parsé devient le timestamp officiel de la ligne `ts_kv`. Si TB est injoignable, le proxy garde le sample en cache SQLite local (déjà parsé) et flushe en POST individuels à la reconnexion (Section 9.2 P8). Pas de batch ni throttle (rate limit proxy → TB levé sur ce déploiement). **L'historique de la panne est intégralement préservé** : chaque sample atterrit dans `ts_kv` au `ts` d'acquisition d'origine.
- **TB device dispatcher** (`heatPumpHybride`, profile `default`) : reçoit la télémétrie de tous les automates sur un seul token TB. Une rule chain lit l'`installation_id` du body et redispatche le payload vers le vrai device PAC (profile `pac hybride`). Trace de passage écrite via `evt_dispatch`. **C'est ce mécanisme qui sépare les installations sans démultiplier les configs proxy.**

Le timestamp d'acquisition est fixé **par l'automate via son RTC** (encodé en string `dateTime`), traduit en epoch ms **par le proxy** au premier passage. TB ne fait que stocker.

### Mesures historiques

ThingsBoard reçoit aujourd'hui des POST de télémétrie **flat** (~275 keys par message) de la part des PAC Hybrides. Mesures du 21-22 mai 2026 :

- 158.7 octets par ligne `ts_kv` (heap + PK btree)
- ~43 KB stockés / post pour 5 KB d'HTTP body (ratio ×8.6, le PK btree pèse plus que la donnée)
- 38% des keys envoyées ne sont jamais lues par les widgets
- Volume `ts_kv_2026_05` à 7.1 GB au 27 mai, +180 MB/jour, dominé à 59% par un seul device
- Extrapolation linéaire : 250 GB / an pour 10 PACs, 750 GB / an pour 30 PACs

Le plan de stockage (memo [project-thingsboard-storage-optim]) a acté une migration vers `json_v` + attributs SERVER_SCOPE, gain stockage ×13.

Ce document spécifie **le contrat firmware → TB**, **le routing rule chain**, **la refonte dashboard**, **la rotation stockage**, et **les exigences firmware** pour la v2. Le mode live (cadence dynamique) est différé (Section 11).

## 2. Goals & non-goals

### Goals

- Définir le contrat JSON nested envoyé par firmware (1 POST = 1 ligne `ts_kv` au lieu de 275)
- Spécifier la rule chain "PAC Hybride Router v2" qui split telemetry / attributs SERVER_SCOPE
- ~~Permettre une cadence dynamique 1 post/min (normal) ↔ 1 post/20 s (mode live quand un client regarde)~~ — **différé** (Section 11), cadence 1/min fixe
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

## 3. Schéma v2 — contrat automate → proxy → TB

> **Statut** : VALIDÉ vérité terrain le 2026-05-29 à partir des payloads réels (automate `2602000001` et `2602000002`) et des décisions utilisateur tranchées en session. Source archivée : `_draft-section3-from-workflow.md` (workflow `wf_6d97a358-298`, 60+ adversarial issues résolues).

### 3.1 Endpoint et flux de transport

```
POST https://bootloader.tsmart.fr/proxy/api/v1/telemetry/tduo
Content-Type: application/json
```

- L'automate POSTe un **body bare** (JSON nu) au proxy.
- Le proxy (`telemetry-proxy 0.1.0` sur `10.77.0.74`, toggle `tb_format=true` actif) :
  1. Parse `dateTime` UTC (format `dd/MM/yy HH:mm:ss`, Rust chrono)
  2. Convertit en epoch ms
  3. Wrap en `{ts, values: <body>}`
  4. Forwarde vers TB (`http://127.0.0.1:8080/api/v1/yDq5GxcbQpuJVgKYRiWu/telemetry`, token du device dispatcher `heatPumpHybride`)
- Le device `heatPumpHybride` (profile `default`) joue le rôle de **dispatcher** : sa rule chain lit `id` du body et redispatche le payload vers le vrai device PAC correspondant (profile `pac hybride`, ex `2602000001`).
- TB stocke en `ts_kv` une ligne par sous-clé après flatten dans la rule chain.

### 3.2 Body format

#### 3.2.1 Body bare (automate → proxy)

Capture réelle (2026-05-29) d'un POST de l'automate `2602000001` (type=0, sans module) :

```json
{
  "id": "2602000001",
  "rel": 1.4,
  "type": 0,
  "nHp": 1,
  "tExt": 33.4,
  "TinM": 6.9,
  "press": 2,
  "commCm2": 0,
  "relCm2": 0,
  "date": "29/05/26",
  "time": "13:05:37",
  "dateTime": "29/05/26 11:05:38",
  "HPs": [ { /* HP1 actif */ }, { /* slot inactif */ }, { /* slot inactif */ }, { /* slot inactif */ } ],
  "heat":   { /* … 14 keys + calo{12} */ },
  "dhw":    { /* … 5 keys + 4 × pump{5} */ },
  "caloM":  { /* … 12 keys */ },
  "pump1M": { /* … 5 keys */ },
  "pump2M": { /* … 5 keys */ }
}
```

#### 3.2.2 Body wrappé (proxy → TB)

```json
{
  "ts": 1780052779000,
  "values": { /* body bare ci-dessus tel quel */ }
}
```

- `ts` = epoch ms calculé depuis `dateTime` UTC du body bare.
- `values` = body bare intégral (les champs `date`, `time`, `dateTime` sont conservés).
- Pas de pretty-print. UTF-8.

### 3.3 Structure nested complète

Les champs marqués `[ATTR]` sont routés en attribut **`SERVER_SCOPE`** par la rule chain TBEL (Section 4). Le firmware envoie tous les champs à chaque cycle ; TB déduplique les attributs (no-op si valeur identique).

#### 3.3.1 Top-level (18 clés)

```yaml
id:       string   # installation_id, ex "2602000001"                            [ATTR]
rel:      number   # version programme régulateur module, ex 1.4                 [ATTR]
type:     integer  # enum 0..3 ; 0=no module, 1=heating, 2=dhw, 3=heating+dhw    [ATTR]
nHp:      integer  # nombre de HPs actifs, 1..4 (0 possible si type=0)           [ATTR]
tExt:     number   # °C température extérieure
TinM:     number   # °C température collecteur primaire module  (T MAJUSCULE — ne pas renommer)
press:    number   # bar pression circuit primaire (plage opération 1..4)
commCm2:  integer  # 0/1 mot de status de communication carte esclave CM2  (télémétrie, pas attribut)
relCm2:   number   # version programme carte esclave CM2 STM32, ex 0           [ATTR]
                   # ⚠ Pas de programme ESP32 dans le module CM2.
date:     string   # "DD/MM/YY" RTC automate, fuseau Europe/Paris (synchro NTP)  (compat widgets dashboard)
time:     string   # "HH:MM:SS" RTC automate, fuseau Europe/Paris                (compat widgets dashboard)
dateTime: string   # "DD/MM/YY HH:MM:SS" UTC — parsé par proxy en ts epoch ms

HPs:      array[4] # voir 3.3.2 — longueur FIXE, slots inutilisés à 0/""
heat:     object   # voir 3.3.3
dhw:      object   # voir 3.3.4
caloM:    object   # voir 3.3.5 — calorimètre MODULE primaire (au root)
pump1M:   object   # voir 3.3.6 — pompe primaire 1 module (Wilo Para Maxo)
pump2M:   object   # voir 3.3.6 — pompe primaire 2 module (Wilo Stratos Maxo)
```

#### 3.3.2 HPs[i] — i = 0..3, longueur fixe 4

Chaque slot représente une PAC individuelle. Les slots `i >= nHp` sont **présents** avec des valeurs à 0 / chaînes vides (cf. 3.4.4).

```yaml
HPs[i]:
  HP:                              # 16 keys — groupe frigorifique
    status:  integer               # code statut PAC (0=OFF, 4=ON, 5=fault, 6=fault gaz, 7=anti-cycle, 9=dégivrage, 10=pump down …)
    pHi:     number   # bar        # pression haute pression
    pLo:     number   # bar        # pression basse pression
    pAir:    integer  # Pa         # pression air
    tIn:     number   # °C         # température entrée eau
    tOut:    number   # °C         # température sortie eau
    tHPf:    number   # °C         # température HP froide
    tHPc:    number   # °C         # température HP chaude
    tLP:     number   # °C         # température BP
    tEvap:   number   # °C         # température évaporation
    tCond:   number   # °C         # température condensation
    tSC:     number   # °C         # sous-refroidissement
    tOH:     number   # °C         # surchauffe
    dpf:     integer               # position détendeur (PAS renommer en eevPos — convention firmware conservée)
    rpm:     integer  # tr/min     # vitesse ventilateur
    time:    integer  # SECONDES   # ⚠ secondes cumulées (impacte widget camembert)

  invert:                          # 8 keys — variateur compresseur (Modbus)
    comm:    bool | integer 0      # cf. note 3.4.3
    freq:    number   # Hz
    volt:    number   # V
    curr:    number   # A
    pwr:     number   # W
    def0:    integer               # code défaut 0
    def1:    integer               # code défaut 1
    def2:    integer               # code défaut 2

  boil:                            # 7 keys — chaudière appoint
    status:  integer               # cf. codes FAULT_LABELS Section 3.5
    tOut:    number   # °C         # sortie chaudière
    tSmoke:  number   # °C         # température fumées
    press:   number   # bar
    qe:      number   # L/h        # débit eau (débitmètre Huba Control 5V)
    rpm:     integer  # tr/min     # vitesse brûleur
    time:    integer  # SECONDES   # ⚠ secondes cumulées (impacte widget camembert)

  pump:                            # 6 keys — pompe PAC dédiée (Wilo Modbus)
    comm:    bool | integer 0      # cf. note 3.4.3
    pwr:     integer  # W
    dP:      number   # mCE        # pression différentielle (renvoyée par la pompe en Modbus)
    qe:      number   # m³/h       # débit (renvoyé direct par la pompe, non transformé)
    rpm:     integer  # tr/min
    time:    integer  # HEURES     # heures cumulées (pas de 10 h renvoyé par la pompe)

  comm:    bool | integer 0        # cf. note 3.4.3
  relStm:  string                  # semver STM32, ex "1.3.137"   ("" si slot inactif)   [ATTR]
  relEsp:  string                  # semver ESP32, ex "1.0.145"   ("" si slot inactif)   [ATTR]
  relScr:  string                  # semver écran tactile, ex "1.0.202" ("" si slot inactif) [ATTR]
```

#### 3.3.3 heat — bloc chauffage (14 keys + calo{12})

```yaml
heat:
  tOut:        number   # °C       # température départ chauffage
  tIn:         number   # °C       # température retour chauffage
  posV3V:      integer  # %        # position vanne 3 voies chauffage
  qeCalc:      integer  # L/h      # débit secondaire chauffage ESTIMÉ

  slope:       number              # pente loi d'eau                            [ATTR]
  foot:        number   # °C       # pied de courbe loi d'eau                   [ATTR]
  tMax:        number   # °C       # consigne max départ chauffage              [ATTR]
  setpoint:    number   # °C       # consigne courante départ chauffage (calculée temps réel)

  dayBgEte:    integer  # DD       # jour début période été                     [ATTR]
  monthBgEte:  integer  # MM       # mois début période été                     [ATTR]
  dayEndEte:   integer  # DD       # jour fin période été                       [ATTR]
  monthEndEte: integer  # MM       # mois fin période été                       [ATTR]

  tCut:        number   # °C       # consigne coupure chauffage (T extérieure)  [ATTR]
  tRes:        number   # °C       # consigne réenclenchement                   [ATTR]

  calo:                            # calorimètre DÉPART CHAUFFAGE (distinct de caloM)
    tIn:    number   # °C
    tRet:   number   # °C          # température retour
    qe:     integer                # débit instantané (unité = qeU)
    qeU:    integer                # code unité Modbus, ex 2875=L/h              [ATTR]
    qeTot:  integer                # débit cumulé (unité = qeTotU)
    qeTotU: integer                # code unité Modbus, ex 3092=0.01 m³          [ATTR]
    pwr:    integer                # puissance instantanée (unité = pwrU)
    pwrU:   integer                # code unité Modbus, ex 2860=10 W             [ATTR]
    hKwh:   integer                # énergie chaud cumulée (unité = hKwhU)
    hKwhU:  integer                # code unité Modbus, ex 3078=kWh / 3079=10kWh [ATTR]
    cKwh:   integer                # énergie froid cumulée (=0 si PAC non réversible)
    cKwhU:  integer                # code unité Modbus                           [ATTR]
```

#### 3.3.4 dhw — bloc ECS (5 keys + 4 × pump{5})

```yaml
dhw:
  tOut:    number   # °C           # température sortie ECS
  tIn:     number   # °C           # température entrée ECS
  tTank:   number   # °C           # température ballon
  tSet:    number   # °C           # consigne ECS                                [ATTR]
  posV3V:  integer  # %            # position V3V ECS primaire

  pump1:                           # primaire 1 (Wilo Modbus)
    pwr:   integer   # W
    dP:    number    # mCE         # pression différentielle (Wilo Modbus)
    qe:    number    # m³/h        # débit (Wilo direct)
    rpm:   integer   # tr/min
    time:  integer   # HEURES      # pas de 10 h
  pump2:                           # primaire 2 (mêmes champs/unités)
  pump3:                           # secondaire 1 (échangeur à plaques, mêmes champs/unités)
  pump4:                           # secondaire 2 (échangeur à plaques, mêmes champs/unités)
```

#### 3.3.5 caloM — calorimètre MODULE primaire

Au root du payload, **distinct** de `heat.calo`. Structure miroir (les codes unité Modbus peuvent différer).

```yaml
caloM:
  tIn:    number   # °C
  tRet:   number   # °C
  qe:     integer                  # débit (unité = qeU)
  qeU:    integer                  # code unité Modbus                           [ATTR]
  qeTot:  integer                  # débit cumulé
  qeTotU: integer                  # code unité Modbus                           [ATTR]
  pwr:    integer                  # puissance
  pwrU:   integer                  # code unité Modbus                           [ATTR]
  hKwh:   integer                  # énergie chaud cumulée
  hKwhU:  integer                  # code unité Modbus                           [ATTR]
  cKwh:   integer                  # énergie froid cumulée
  cKwhU:  integer                  # code unité Modbus                           [ATTR]
```

#### 3.3.6 pump1M, pump2M — pompes primaires module

Wilo Para Maxo (pump1M) et Wilo Stratos Maxo (pump2M), Modbus.

```yaml
pump1M:
  pwr:   integer   # W
  dP:    number    # mCE
  qe:    number    # m³/h
  rpm:   integer   # tr/min
  time:  integer   # HEURES        # pas de 10 h
pump2M:
  # mêmes champs / mêmes unités
```

### 3.4 Notes, types, pièges

#### 3.4.1 Types numériques inhabituels

- `rel` et `relCm2` sont des **numbers** (pas strings). Choix firmware. Ex `rel = 1.4`, `relCm2 = 0`.
- `relStm` / `relEsp` / `relScr` sont en revanche des **strings semver 3-level** (`"1.3.137"`, `"1.0.145"`, `"1.0.202"`).
- Pas de programme ESP32 dans le module CM2 — `relCm2` documente uniquement le firmware STM32 esclave.

#### 3.4.2 Casse et nommage préservés

- `TinM` (T **MAJUSCULE**) : convention firmware module. **Ne pas renommer** en `tInM`. La clé `tInM` (lowercase) qui traîne dans `ts_kv_latest` est un historique pré-v2, sera purgée par rotation TTL.
- `dpf` (et `HP{i}_dpf` après flatten) : convention firmware conservée. **Ne pas renommer** en `eevPos`.
- `type` : conservé tel quel (pas renommé `modType`).

#### 3.4.3 Champs `comm` : booléen vs integer 0 (transitoire)

- Type cible : **boolean partout** (firmware final).
- Firmware de **certification actuel** : `comm` hardcodé à `integer 0` pour les slots `HPs[1..3]` non implémentés (structures `pac2/pac3/pac4` pas encore dans le code de cert). Dans `HPs[0]` et autres `comm` actifs : vrai booléen.
- Spec déclare : `comm: bool | integer 0`. Le consommateur TB doit accepter les deux.
- S'applique à : `HPs[i].comm`, `HPs[i].invert.comm`, `HPs[i].pump.comm`. **Ne s'applique pas** à `commCm2` (top-level) qui reste un integer 0/1 status.

#### 3.4.4 Slots HPs[i] inactifs (i >= nHp)

- Numérics → `0`
- Strings semver (`relStm`, `relEsp`, `relScr`) → `""` (chaîne vide)
- Booléens `comm` → `0` (integer, cf. 3.4.3)
- Tous les sous-objets `HP/invert/boil/pump` sont **présents** avec valeurs à 0
- Avantage : flatten déterministe en rule chain → `HP1_*`, `HP2_*`, `HP3_*`, `HP4_*` toujours présents en `ts_kv`

#### 3.4.5 Installations sans module (`type = 0`)

- Tous les blocs nested (`HPs`, `heat`, `dhw`, `caloM`, `pump1M`, `pump2M`) sont **présents** avec valeurs à 0 (ou chaînes vides pour les strings).
- Seuls `id`, `rel`, `type`, `nHp`, `tExt`, `TinM`, `press`, `commCm2`, `relCm2`, `date`, `time`, `dateTime` portent leurs vraies valeurs.
- **Reportées sur TB normalement** — le contrat v2 ne les exclut pas.

#### 3.4.6 Format `dateTime`

L'automate formate avec `sprintf("%02d/%02d/%02d %02d:%02d:%02d", jour, mois, annee%100, heure, minute, seconde)` en UTC.

- Séparateur : `/` entre date, `:` entre heure, espace entre date et heure
- Année sur 2 chiffres (modulo 100) ; limitation connue pour 2100+
- **UTC obligatoire** (le proxy parse en TZ serveur = UTC)
- `date` et `time` séparés (fuseau Europe/Paris) sont gardés en parallèle pour compat widgets dashboard existants

#### 3.4.7 Contraintes encodage

- JSON sans pretty-print (pas de retours ligne ni d'espaces superflus)
- UTF-8
- Booléens encodés `true`/`false` quand actifs, ou `0` (integer) pour les slots inactifs (transition firmware)

### 3.5 Flux `evt_*` — POSTs ad-hoc (séparé du nested cyclique)

Les clés `evt_*` ne font **pas partie du payload nested régulier**. Ce sont des télémétries POSTées séparément lors de changements d'état (apparition / disparition de défaut), plus des traces internes du dispatcher.

Inventaire validé en prod 2026-05-29.

#### 3.5.1 Bundle défaut (apparition / disparition)

Co-écrit en un seul POST au même `ts` (~3 events/24h par device en fonctionnement nominal).

| Clé | Type TB | Rôle | Devices |
|---|---|---|---|
| `evt_date` | string | Date de l'événement, `dd/MM/yy` (fuseau Paris) | `heatPumpHybride`, `2602000001`, `2602000002` |
| `evt_time` | string | Heure de l'événement, `HH:mm:ss` (fuseau Paris) | idem |
| `evt_device` | long | ID sous-équipement source (0 = base, 50 = dispatcher self, autres = HP/module) | idem |
| `evt_fault` | long | **Code défaut** (cf. table 3.5.4) | idem |
| `evt_status` | long | `1 = apparition` défaut / `0 = disparition` défaut | idem |
| `evt_type` | long | Catégorie événement (0/1 observés) | idem |

#### 3.5.2 Corrélation défaut

| Clé | Type TB | Rôle | Devices |
|---|---|---|---|
| `evt_id` | long | **Timestamp epoch SECONDES** (pas ms !) du dernier événement — corrèle `evt_date`+`evt_time` | `2602000001`, `2602000002` |

Écrite séparément du bundle, avec son propre `ts`. ⚠ Ratio s vs ms à respecter dans les widgets de corrélation.

#### 3.5.3 Traces dispatcher

Émises uniquement sur le device virtuel `heatPumpHybride`.

| Clé | Fréquence 24h | Rôle |
|---|---|---|
| `evt_dispatch` | ~3265 (~2.27/min) | Trace de routage — `str_v` = id routé via FIFO N |
| `evt_no_id` | ~16 | Payload reçu sans champ `id` — rejeté par dispatcher |
| `evt_unknown_id` | ~30 | `id` présent mais inconnu du mapping |
| `evt_provision` | ~22 | Création/association device suite à `id` inconnu (log provisioning) |

#### 3.5.4 Table des codes `evt_fault` (FAULT_LABELS)

Interprétation côté serveur, source de vérité dans le widget `tduo.fault_diagnostic` (TB). Tableau complet 114 codes (0..113) :

| Code | Libellé FR | Code | Libellé FR | Code | Libellé FR |
|---|---|---|---|---|---|
| 0 | (vide) | 38 | Defaut communication | 80 | Defaut pression HP |
| 1 | Defaut sonde depart | 39 | Defaut communication | 81 | Defaut pression BP |
| 2 | Defaut sonde retour | 40 | Defaut communication | 82 | **Gaz detecte** |
| 3 | Defaut sonde fumee | 41 | Pression trop faible | 83 | Defaut surchauffe chaud. |
| 4 | Defaut sonde pression | 42 | Redemarrage regulateur | 84 | Defaut com. pompe |
| 5 | Defaut debit eau | 43 | Manipulation tactile | 85 | Defaut com. compresseur |
| 6 | Defaut surpression eau | 44 | Filtre encrasse | 86 | Defaut com. gaz G20 |
| 7 | Surchauffe | 45 | Defaut carte 1 | 87 | Defaut com. gaz R290 |
| 8 | Defaut bruleur | 46 | Defaut carte 2 | 88 | Defaut communication |
| 9 | Defaut ventil. bruleur | 47 | Defaut carte 3 | 89 | Defaut pression eau |
| 10 | Defaut preventilation | 48 | Defaut carte 4 | 90 | Defaut HP max |
| 11 | Defaut delta temp. | 49 | Defaut carte 5 | 91 | Defaut BP min |
| 12 | Defaut temp. fumee | 50 | Defaut carte 6 | 92 | Defaut variateur 0Hz |
| 13 | Defaut circuit fumee | 51 | Defaut carte 7 | 93 | Defaut variateur |
| 14 | Bruleur non linearise | 52 | Defaut bruleur 8 | 94 | Defaut surchauffe PAC |
| 15 | Defaut communication | 53 | Defaut bruleur 9 | 95 | Defaut T sortie PAC |
| 16 | Defaut sous-tension | 54 | Defaut bruleur 10 | 96 | Defaut T entree PAC |
| 17 | Defaut surtension | 55 | Defaut bruleur 11 | 97 | Defaut T BP |
| 18 | Manque phase | 56 | Defaut bruleur 12 | 98 | Defaut T HP chaud |
| 19 | Marche a sec | 57 | Defaut bruleur 13 | 99 | Defaut T HP froid |
| 20 | Pression trop forte | 58 | Defaut interne boitier | 100 | Defaut pression eau bas |
| 21 | Pression trop faible | 59 | Defaut general boitier | 101 | Defaut pression eau haut |
| 22 | Moteur trop chaud | 60 | Nb max reset atteint | 102 | Defaut pression air |
| 23 | Defaut moteur | 61 | Defaut pompe ECS | 103 | Defaut vitesse ventilateur |
| 24 | Pompe bloquee | 62 | Defaut module FTP | 104 | Defaut sonde T entree module |
| 25 | Surchauffe module | 63 | Defaut pression fumee | 105 | Defaut sonde T exterieure |
| 26 | Avertissement module | 70 | Defaut sonde T entree chaud. | 106 | Defaut sonde T sortie ECS |
| 27 | Defaut module | 71 | Defaut sonde T sortie chaud. | 107 | Defaut sonde T entree ECS |
| 28 | Defaut capteur | 72 | Defaut sonde T fumee chaud. | 108 | Defaut sonde T sortie chauffage |
| 29 | Defaut communication | 73 | Defaut sonde T entree PAC | 109 | Defaut sonde T entree chauffage |
| 30 | Defaut vanne eau | 74 | Defaut sonde T BP | 110 | Defaut sonde T stockage |
| 31 | Utilisation excessive | 75 | Defaut sonde T HP-h | 111 | Gaz R290 détecté |
| 32 | Adaptation plage | 76 | Defaut sonde T HP-c | 112 | Gaz G20 détecté |
| 33 | Surcharge mecanique | 77 | Defaut sonde T air ext. | 113 | Defaut temperature sortie chaudiere |
| 34 | Defaut securite | 78 | Defaut pression air | | |
| 35 | Erreur test clapet | 79 | Defaut pression eau | | |
| 36 | Temperature trop elevee | | | | |
| 37 | Fumee detectee | | | | |

Note : les codes 64-69 n'existent pas dans la table actuelle (réservés). Cette table est maintenue dans `widget_type` où `fqn='tduo.fault_diagnostic'` (variable JS `FAULT_LABELS`).

#### 3.5.5 Devices émetteurs (UUIDs TB)

| Device | UUID |
|---|---|
| `heatPumpHybride` (dispatcher virtuel) | `2de23ab0-3e51-11f1-bbfe-e1395562cba0` |
| `2602000001` | `b16d15b0-4227-11f1-bbfe-e1395562cba0` |
| `2602000002` | `2bceaf80-42dc-11f1-bbfe-e1395562cba0` |

`2610000001` et `2602000003` mentionnés en mémoire mais pas encore actifs en TB.

### 3.6 Récapitulatif `[ATTR]` — paths attributs SERVER_SCOPE

Champs routés en attribut par la rule chain TBEL (Section 4). Constants par device, mis à jour seulement sur changement.

| Bloc | Champs `[ATTR]` | Compte |
|---|---|---|
| top-level | `id`, `rel`, `type`, `nHp`, `relCm2` | 5 |
| `HPs[i]` (× 4 slots fixes) | `relStm`, `relEsp`, `relScr` | 12 |
| `heat` | `slope`, `foot`, `tMax`, `dayBgEte`, `monthBgEte`, `dayEndEte`, `monthEndEte`, `tCut`, `tRes` | 9 |
| `heat.calo` | `qeU`, `qeTotU`, `pwrU`, `hKwhU`, `cKwhU` | 5 |
| `dhw` | `tSet` | 1 |
| `caloM` | `qeU`, `qeTotU`, `pwrU`, `hKwhU`, `cKwhU` | 5 |
| **Total** | | **37** |

Les autres champs (`tExt`, `TinM`, `press`, `commCm2`, `date`, `time`, `dateTime`, contenus `HPs[i].HP/invert/boil/pump`, `heat.tOut/tIn/posV3V/qeCalc/setpoint`, `heat.calo.tIn/tRet/qe/qeTot/pwr/hKwh/cKwh`, `dhw.tOut/tIn/tTank/posV3V/pumpN.*`, `caloM.tIn/tRet/qe/qeTot/pwr/hKwh/cKwh`, `pump1M/2M.*`) sont en télémétrie horodatée standard.

## 4. Rule chain "PAC Hybride Router" — extension v2

> **Décisions actées** (2026-05-29 point 2) :
> - **Option B** : double écriture flat + json_v en parallèle pendant la transition Phase 3 (refonte widgets). Coût stockage transitoire +7 %.
> - **Insertion dans la rule chain existante** `PAC Hybride Router` (UUID `b6af0570-4226-11f1-bbfe-e1395562cba0`), pas de nouvelle rule chain.
> - **Déploiement via REST API JSON** (UI manuelle non praticable). Procédure Section 4.6.

### 4.1 État actuel de la rule chain

Déployée et opérationnelle. 13 nodes :

```
[id present?] (filter JS sur msg.id)
   │
   ├─ no  → [wrap evt_no_id] → [save evt_no_id]  (telemetry sur dispatcher heatPumpHybride)
   │
   └─ yes → [extract id → metadata]
                 │
                 ▼
            [originator → device(${id})] (ChangeOriginator : redirige vers device PAC réel par nom)
                 │
                 ├─ device inconnu → [wrap evt_unknown_id] → [save evt_unknown_id] + [alarm UnknownInstallation]
                 │
                 └─ device existant → [mark active] → [save active attrs]
                                              │
                                              ▼
                                      [save TS (per-id device)]   ← écrit body en FLAT keys (HP1_*, dhw_*, etc.)
                                              │
                                              ▼
                                      [DeviceProfile (alarms)] → [alarm MalformedPayload] si applicable
```

C'est ce flow qui produit aujourd'hui les ~247 keys flat sur les vrais devices PAC (`2602000001`, `2602000002`, …).

### 4.2 Extension v2 — insertion de 4 nouveaux nodes

Après `mark active`, on insère 4 nouveaux nodes **en parallèle** de `save TS (per-id device)` :

```
[mark active] ─┬─► [save TS (per-id device)]                                              ← GARDÉ (Option B)
               │     └─► [DeviceProfile (alarms)]                                          (chaîne existante)
               │
               └─► [4.3 TBEL : split-attributes-from-payload]                              ← NOUVEAU
                          │
                          ▼
                    [4.4 Message Type Switch]
                          │
                          ├─ Post attributes  → [4.5 Save Attributes SERVER_SCOPE]         ← NOUVEAU
                          │
                          └─ Post telemetry   → [4.5 Save Timeseries (key=pac_v2)]         ← NOUVEAU
```

Résultat 13 + 4 = 17 nodes. Chaque sample reçu produit :

- 1 ligne `attribute_kv` par attribut SERVER_SCOPE (no-op si valeur inchangée — TB déduplique)
- 247 lignes `ts_kv` flat (chaîne existante, inchangée)
- 1 ligne `ts_kv` avec `key=pac_v2` et `value_json = <payload nested sans attrs>` (nouvelle)

### 4.3 Script TBEL "split-attributes-from-payload"

Le `ts` d'acquisition est déjà dans `metadata.ts` (injecté par le proxy via le wrapper `{ts, values}`). Le script ne fait que le split attributs / payload.

**Paths attributs (28 templates → 37 attrs au runtime avec HPs × 4)** :

```javascript
// scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel
//
// Reçoit un msg nested v2 (msg.HPs présent).
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

> **Validation TBEL** : la syntaxe `foreach`, `clone()`, `metadata.merge()`, `.remove()` doit être validée contre TB 4.3 avant déploiement. Si une primitive manque, fallback sur un node JavaScript (`TbJsTransformNode`) avec sémantique identique (légèrement plus lent au runtime mais sans impact à cadence 1/min).

### 4.4 Node "Message Type Switch"

Le TBEL retourne **2 messages** dans la même réponse, tous deux émis sur la sortie `Success`. Il faut router chaque message vers le bon node de stockage en fonction de son `msgType` :

- Type node : `org.thingsboard.rule.engine.flow.TbMsgTypeSwitchNode`
- Le node a des sorties nommées par type de message ; on connecte :
  - sortie `Post attributes request` → Save Attributes (4.5)
  - sortie `Post telemetry request`  → Save Timeseries (4.5)

### 4.5 Nodes Save Attributes + Save Timeseries

#### Save Attributes (SERVER_SCOPE)

- Type : `org.thingsboard.rule.engine.telemetry.TbMsgAttributesNode`
- Configuration : `scope = SERVER_SCOPE`, `notifyDevice = false`, `sendAttributesUpdatedNotification = true`
- Comportement : lit `msg` (objet plat `{id, rel, type, nHp, relCm2, dhw_tSet, heat_slope, ..., HP1_relStm, HP2_relStm, ...}`) et écrit chaque clé en attribut SERVER_SCOPE du device originator (post-ChangeOriginator).

#### Save Timeseries (key=pac_v2 json_v)

- Type : `org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode`
- Configuration : `useServerTs = false` (utilise `metadata.ts`), `defaultTTL = 0` (illimité, géré par cron Section 8)
- Comportement : prend `msg = { pac_v2: <payload nested> }`, écrit 1 ligne `ts_kv` avec `key = pac_v2` et `value_json = <payload>` au `ts = metadata.ts`.

### 4.6 Procédure de déploiement (REST API JSON)

UI manuelle non praticable — modif via REST API obligatoire. Le script de déploiement est dans la Phase 1 du plan d'implémentation (`scripts/tb/rule-chain-pac-hybride-router/deploy-v2-nodes.ps1`).

#### Étapes

1. **Authentification** : récupérer un JWT tenant admin.
2. **Backup** : `GET /api/ruleChain/b6af0570-4226-11f1-bbfe-e1395562cba0/metadata` → sauvegarder en `scripts/tb/backup/rule-chain-pac-hybride-router-pre-v2.json`.
3. **Modification du JSON** : insertion programmatique des 4 nouveaux nodes dans le tableau `nodes` + des connexions associées dans `connections` :
   - Connexion existante `mark active → save TS (per-id device)` : conservée.
   - Nouvelle connexion `mark active → TBEL split` (type `Success`).
   - Nouvelle connexion `TBEL split → Message Type Switch` (type `Success`).
   - Nouvelle connexion `Message Type Switch → Save Attributes` (type `Post attributes`).
   - Nouvelle connexion `Message Type Switch → Save Timeseries pac_v2` (type `Post telemetry`).
4. **Validation** : `POST /api/ruleChain/{id}/metadata` avec le JSON modifié.
5. **Vérification fumée** : envoyer 1 POST factice via curl à l'endpoint proxy avec un body v2, vérifier en SQL :

   ```sql
   -- 1 ligne pac_v2 récente
   SELECT to_timestamp(ts/1000), length(json_v::text)
   FROM ts_kv_2026_05
   WHERE entity_id = (SELECT id FROM device WHERE name='2602000001')
     AND key = (SELECT key_id FROM key_dictionary WHERE key='pac_v2')
   ORDER BY ts DESC LIMIT 1;

   -- Attributs SERVER_SCOPE populés
   SELECT count(*)
   FROM attribute_kv
   WHERE entity_id = (SELECT id FROM device WHERE name='2602000001')
     AND attribute_type = 'SERVER_SCOPE';
   ```

   Attendu : 1 ligne pac_v2 (~3 KB JSON), ≥ 30 attributs SERVER_SCOPE.

6. **Rollback** : `POST /api/ruleChain/{id}/metadata` avec le backup pre-v2. Le device retombe en double-écriture sans le pac_v2 supplémentaire.

#### Outils

- **PowerShell** : `Invoke-RestMethod` pour les appels REST.
- **Python** : alternative possible (`requests` + `json`), choix au moment de l'écriture du script.
- Le script doit être **idempotent** : si les nouveaux nodes existent déjà (détectés par nom unique `TBEL split v2`, `MsgType Switch v2`, `Save Attrs v2`, `Save TS pac_v2`), il met à jour leur configuration sans dupliquer.

### 4.7 Nommage des clés produites

- **Telemetry key** : `pac_v2` (fixe, versionnée — évolution future possible vers `pac_v3` sans casser les widgets v2)
- **Attributs root** : `id`, `rel`, `type`, `nHp`, `relCm2`, `dhw_tSet`, `heat_slope`, …, `heat_calo_qeU`, …, `caloM_qeU`, …
- **Attributs HPs** : `HP1_relStm`, `HP1_relEsp`, `HP1_relScr`, `HP2_relStm`, …, `HP4_relScr` (12 attributs HPs)
- Format du path attribut : dotted path source joiné par `_`. Exemple `heat.calo.qeTotU` → `heat_calo_qeTotU`.

### 4.8 Cas d'erreur

- **Body mal formé** (HPs présent mais clé attribut manquante) : le script saute le champ via la garde `!= null`. Aucun crash.
- **Save Timeseries failure** : message routé sur output `Failure` du node, à diriger vers une queue/log standard TB. La ligne flat parallèle continue d'être écrite (Option B).
- **Attribut volumineux** (`str_v > 255` bytes) : à surveiller périodiquement via `SELECT max(length(str_v)) FROM attribute_kv`. Si dépassement, restreindre `ATTR_PATHS` ou tronquer dans le TBEL.
- **TBEL syntax error** : message en `Failure`, save flat continue, à logger.

### 4.9 Évolution Phase 3 (refactor widgets)

Quand les widgets dashboard auront été refactorisés pour lire `pac_v2` json_v (Phase 3 du plan d'implémentation) :

1. Supprimer la connexion `mark active → save TS (per-id device)` (le node existe encore mais n'est plus exécuté).
2. Optionnel : supprimer le node `save TS (per-id device)` entièrement.
3. Volume `ts_kv` chute de ~247 lignes/sample à ~1 ligne/sample → gain ×~250 sur ce flux.
4. Les attributs SERVER_SCOPE produits par le TBEL split deviennent la seule source pour les versions / consignes / unités calo.

## 5. Mode live — DIFFÉRÉ

> **Statut (2026-05-29 point 3)** : Le mode live (cadence dynamique 1/min ↔ 20 s déclenchée par la présence d'un utilisateur sur la page détail) **n'est pas implémenté**. Décision utilisateur : pas dans cette phase, à reconsidérer dans plusieurs jours.
>
> **Cadence opérationnelle** : **1 POST / min fixe**. L'automate envoie en continu à cette cadence, le dashboard rafraîchit toutes les minutes avec le dernier `pac_v2`.
>
> Le design complet (widget keep-alive SHARED_SCOPE, rule chain "Live Timeout Sweep" cron, discovery proxy P7) est archivé en **Section 11 — Décisions différées** pour réactivation future. Aucun attribut `SHARED_SCOPE` n'est utilisé dans le contrat v2 actuel.

## 6. Migration : proxy d'abord, puis cutover payload v2 par device via OTA

### Phasage

Deux phases distinctes :

**Phase 0 — Proxy** (avant tout autre changement). Mise en place du proxy en mode pur passthrough pour le **format flat actuel**. À la fin de la phase, tous les devices passent par le proxy mais envoient toujours du flat ; TB reçoit exactement la même chose qu'aujourd'hui. Le proxy n'a pas encore besoin de gérer `live` puisque le firmware actuel ne fait pas de mode live.

**Phase 1+ — Payload v2** (rule chain + widgets + automate v2). Une fois Phase 0 stable, on déploie tout le reste (Sections 3, 4, 7, 8). Le mode live (Section 5) est différé (cadence 1/min fixe).

### Phase 0 — Proxy ✅ DONE 2026-05-28

Le proxy était déjà déployé en mode legacy (passthrough). La bascule en mode v2 a été faite et validée en prod le 2026-05-28.

| Étape | Action | Validation | Statut |
|---|---|---|---|
| P0.1 | Activer le mode v2 sur device "tduo" via toggle config (`tb_format=true`) | Le proxy parse `dateTime` UTC, wrap `{ts, values}`, forwarde à TB. Lignes `ts_kv` apparaissent au ts d'acquisition | ✅ DONE |
| P0.2 | Test scénario cache offline : `systemctl stop thingsboard` 5 min, vérifier cache, restart, vérifier replay | Cache passé 0 → 11 entrées pendant la coupure 16:55-17:00 UTC. Replay automatique en ~60 s. Devices `2602000001`/`2602000002` reçoivent 5 samples × 247 keys au `ts` d'origine | ✅ DONE |
| P0.3 | Validation rollback toggle | Pas effectué — mode v2 jugé stable, kept ON | ✅ N/A |
| P0.4 | Rollout sur tous les devices du parc | Le proxy n'a qu'1 entrée `devices.tduo` qui couvre les 2 automates actifs (`2602000001`, `2602000002`). Le 3e (`2610000001`) et le 4e (`2602000003`) déjà alignés sur la même URL d'ingest | ✅ DONE |
| P0.5 | ~~Activer la logique `live` discovery (P6/P7) dans le proxy~~ | **Différé** — mode live drop (Section 11) | ⏸️ DIFFÉRÉ |
| P0.6 | Bugs d'affichage UI proxy `https://bootloader.tsmart.fr/proxy/ui` | À investiguer/corriger | ⏳ TODO |

### Phase 1+ — Cutover payload v2 (par device via OTA)

Pas de shadow write. La rule chain gère simultanément les deux formats (nested v2 et flat ancien) via le `Switch` sur `msg.HPs`. Chaque device flippe au gré de son OTA. Tous les devices passent déjà par le proxy depuis Phase 0.

| Jour | Action | Risque rollback |
|---|---|---|
| J0 | Deploy rule chain v2 (les 2 branches actives, aucun device en nested encore) | Revert rule chain version |
| J0 | Deploy widgets TDUO refactorisés sur dashboard | Revert dashboard json |
| J0 | Setup cron PG `tb-ts_kv-drop-old-year.sh` (Section 8) | Désactiver le cron |
| J+1 | Pilot OTA automate v2 sur 1 device test | Revert firmware sur ce device |
| J+1 | Validation : ligne `pac_v2` apparaît dans `ts_kv`, attributs SERVER_SCOPE présents dans `attribute_kv` | n/a |
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
| `default` | Unité | false | **Refonte complète** : Hub Info + Heating Loop Card + DHW Card + N × PAC Synoptic + Boiler Synoptic (conditionnel sur présence chaudière) |
| `donnees_HP1` | Données détaillées PAC | false | **Refonte** : 1 × PAC Synoptic en pleine page (lit `pac_v2.HPs[selected].*`) |
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

`<proxy_host>` est l'adresse du proxy (LAN local typiquement). Le proxy forwarde vers `thingsboard.tsmart.fr` sans modification d'URL. Pas de query param spécial.

Body wrappé `{ ts, values }` (Section 3) pour préserver le timestamp d'acquisition côté automate :

```json
{ "ts": 1716902040000, "values": { "...nested payload v2..." } }
```

#### M2 — Cadence

- **Mode normal** : 1 POST / 60 s
- **Cadence fixe** (mode live différé en Section 5/11)

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

#### M6 — Mode live (DIFFÉRÉ)

Voir Section 5 / Section 11. L'automate ignore tout body de réponse spécifique, traite le 200 OK standard.

#### M7 — Encodage

- UTF-8 sans BOM
- Floats max 1 décimale (sauf strings de version `"1.04"`)
- Booléens : integer `0` / `1`
- Pas de retours ligne dans le JSON
- Content-Length set correctement

#### M8 — Retry réseau côté automate

Le cache offline est **délégué au proxy** (Section 9.2). L'automate fait du retry simple côté HTTP :

- Sur timeout / erreur 5xx du proxy : max 3 retries avec backoff `5, 15, 60` s
- Au-delà : abandon de ce sample (le proxy est censé absorber les pannes TB ; un échec persistant proxy → automate est probablement un problème de LAN à investiguer)

L'automate n'a pas besoin de cacher lui-même : le proxy le fait pour les samples destinés à TB.

#### M9 — Compatibilité firmware ancien

Pendant la phase de rollout, certains devices ne sont pas encore reliés à l'automate middleware et POSTent directement en format flat ancien. La rule chain TB accepte les deux formats (Section 4) sans coordination supplémentaire.

#### M10 — Modification setpoints

**Hors scope payload v2.** Les consignes sont modifiées par voie locale (écran physique du firmware, LAN, BLE). Le firmware remonte les setpoints courants à l'automate via Modbus ; l'automate les remonte dans le payload via les champs `[ATTR]`. TB **n'est jamais source de vérité** pour les setpoints.

### 9.2 Proxy — ✅ IMPLÉMENTÉ ET VALIDÉ EN PROD 2026-05-28

Composant intercalé entre l'automate et TB. Rôle : **enrichir avec `ts` à partir de `dateTime` + relay HTTP + cache offline**.

**Statut concret** :
- Binary Rust `telemetry-proxy 0.1.0` à `/usr/local/bin/telemetry-proxy`, service systemd `telemetry-proxy.service`
- Config JSON `/etc/telemetry-proxy/config.json`, format documenté en config.example
- UI admin à `https://bootloader.tsmart.fr/proxy/ui` (login yahtec)
- Cache SQLite `/var/lib/telemetry-proxy/cache.db` (table `pending(id, device, body BLOB, headers TEXT, created_at, attempts)`)
- Validation test rupture TB 5 min OK (voir frontmatter spec)

**Toggle deux modes** : champ `devices.<name>.tb_format` (bool) dans la config :
- **`tb_format: false`** (mode legacy) : passthrough pur, aucune transformation. Body forwardé tel quel à TB.
- **`tb_format: true`** (mode v2, **activé pour `tduo` depuis 2026-05-28**) : parse `dateTime` UTC (format `dd/MM/yy HH:mm:ss`, Rust chrono `%d/%m/%y %H:%M:%S`) + wrap `{ts, values}` + cache offline avec rejeu à la reconnexion. Comportement décrit P1-P8.

Le toggle est appliqué par device (alias dans l'URL `/api/v1/telemetry/<device>` ↔ entrée `devices.<device>` dans la config). Permet un rollout progressif et un rollback instantané sans redéployer le proxy (toggle via UI ou edit config + SIGHUP/file watch).

#### P1 — Transformation à chaque forward

Le proxy fait **deux transformations** sur chaque body reçu de l'automate :

1. **Parse `dateTime`** (`"JJ/MM/AA HH:MM:SS"`) en epoch ms. Pseudo-code Python :
   ```python
   from datetime import datetime
   ts_ms = int(datetime.strptime(body["dateTime"], "%d/%m/%y %H:%M:%S").timestamp() * 1000)
   ```
   (équivalents Go `time.Parse("02/01/06 15:04:05", ...)`, Node `Date.parse(...)`, etc.)
2. **Wrap en `{ts, values}`** : nouveau body =
   ```json
   { "ts": <ts_ms>, "values": <body_original_intact> }
   ```

URL / headers / méthode HTTP : **inchangés**. Le proxy ne touche pas à `Content-Type`, l'auth, l'endpoint TB.

Du point de vue de TB : la requête est une POST telemetry standard avec wrapper `{ts, values}`. TB stocke la ligne `ts_kv` au `ts` parsé.

#### P2 — Forwarding nominal

Quand TB est joignable :
1. Receive POST de l'automate (body bare avec `dateTime` string)
2. Parse + wrap (P1)
3. Forward HTTPS à TB avec le body wrappé
4. Receive response TB
5. Forward response à l'automate (200 OK standard ; pas d'injection `live` — mode live différé)

Latence ajoutée : ~1 ms de parsing + 1 hop TCP.

#### P3 — Comportement cache hors-ligne

Quand TB est injoignable (timeout, 5xx, erreur DNS) :
1. Receive POST de l'automate
2. Effectuer la transformation P1 immédiatement (parse + wrap) — le `ts` est figé dès l'arrivée
3. **Persister** le body wrappé `{ts, values}` sur disque local du proxy (FIFO)
4. Répondre 200 OK à l'automate (body neutre, mode live différé)
5. En tâche de fond, retenter `GET https://thingsboard.tsmart.fr/` (healthcheck léger) avec backoff exponentiel (60 s, 120 s, 240 s, max 600 s)
6. À la reconnexion TB : flusher les samples cachés en POST individuels FIFO (Section P8). Pas de batch, pas de throttle (le rate limit entre proxy et TB est levé sur ce déploiement)
7. **Historique préservé** : 1 h de panne = 60 samples bufferisés = 60 lignes `ts_kv` distinctes à leurs `ts` d'acquisition respectifs après flush
8. Si une requête flushée échoue (TB répond 4xx — payload invalide) : log et drop ce sample, ne bloque pas la file. Si TB répond 5xx au milieu du flush, retourner à l'état déconnecté et garder le reste du cache pour le prochain cycle

#### P4 — Capacité buffer

Minimum recommandé : **24 h de samples** = 1 440 × ~3 KB = ~5 MB. Le proxy est typiquement sur un mini-PC LAN ou un raspberry, donc dimensionnable beaucoup plus large (Go disponibles). Politique d'éviction si plein : FIFO drop des plus anciens.

#### P5 — Idempotence et déduplication

TB **n'a pas** de mécanisme natif de déduplication sur `ts`. Si le proxy rejoue 2× la même requête (ex : redémarrage du proxy avec un sample partiellement persisté), TB écrira **2 lignes** dans `ts_kv` avec le même `ts`. Conséquence : valeur dupliquée dans les charts.

Mitigation : le proxy maintient un compteur de séquence ou un hash du body pour éviter le re-POST d'une même requête au sein d'une session. Détail d'implémentation, hors spec.

#### P6 et P7 — Mode live (DIFFÉRÉ)

Voir Section 11. Le proxy ne fait actuellement **aucune** logique `live` : ni discovery vers TB, ni injection dans la réponse à l'automate. Toggle `tb_format=true` actif pour `dateTime`+wrap mais sans gestion `live`.

#### P8 — Flush du cache

À la reconnexion TB, le proxy envoie chaque sample du cache en **POST individuel** dans l'ordre FIFO :

```
for each cached_wrapped_body in cache[token]:
    response = POST https://thingsboard.tsmart.fr/api/v1/{token}/telemetry
               body = cached_wrapped_body   # déjà {ts, values}
    if response.status >= 500:
        # TB est retombé, on garde le reste pour plus tard
        break
    if response.status >= 400:
        # payload mal formé sur ce sample, on log et on continue
        log_drop(cached_wrapped_body)
    pop_from_cache()
```

Pas de batch endpoint, pas de throttle : le rate limit entre proxy et TB est levé sur ce déploiement. TB encaisse N POST en rafale, chacun écrit 1 ligne `ts_kv` à son `ts` d'acquisition.

**Calcul volume** :
- Pire cas pratique : 24 h de panne × 1 device à cadence 1/min = **1 440 samples** = 1 440 POST séquentiels = ~1 minute de drain par device
- 30 devices reconnectent en même temps = 30 drains parallèles, chacun ~1 min
- Plus de 7 jours de panne = 10 080 samples = ~7 min de drain par device. Pas un cas opérationnel attendu.

**Ordre FIFO** préservé dans le drain, mais TB stocke chaque sample à son `ts` propre — l'ordre d'arrivée à TB n'a aucun impact sur la timeline finale dans `ts_kv`.

## 10. Inventaire composants

### À modifier

| Composant | Type | Action |
|---|---|---|
| Rule chain "PAC Hybride Router" | TB rule chain | **Remplacer** (Section 4) |
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
| Proxy | Code séparé (déjà déployé) | **Activer le mode v2 via toggle config** (Section 9.2, P1-P8). Code de parse `dateTime` + wrap déjà présent dans le proxy, juste à activer |
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
- **Extension TB `postTelemetry?withSharedKeys=live`** : initialement prévue (patch sur `DeviceApiController.java` côté fork yahtec) pour éviter au client un GET attributes séparé. Décision actuelle : pas implémentée puisque le mode live lui-même est différé (voir ci-dessous). Le design Java reste valable, archivé dans l'historique git de cette spec.

### 11.1 Mode live — design archivé (différé 2026-05-29)

Décision utilisateur : **pas dans cette phase, à reconsidérer dans plusieurs jours**. Cadence actuelle = 1 POST/min fixe.

Le design complet ci-dessous est conservé pour réactivation future sans avoir à le re-concevoir.

#### Mécanique côté dashboard

Un utilisateur ouvre un state qui doit "vivre" en temps réel (typiquement `default` ou `donnees_HP1` du dashboard "Mes Installations"). Le widget custom JS au mount :

1. Écrit `SHARED_SCOPE live=true` + `liveTs=Date.now()` via `ctx.attributeService.saveEntityAttributes()`
2. Démarre un setInterval 60 s qui rewrite `liveTs=Date.now()` tant que `document.visibilityState === 'visible'`
3. Au unmount / blur / visibilitychange→hidden / beforeunload : écrit `SHARED_SCOPE live=false`

#### Mécanique côté automate

L'automate lit `live` **dans la réponse de son POST telemetry au proxy** (le proxy injecte la valeur depuis sa connaissance interne) :

- Si `shared.live === true` → cadence = 20 s
- Sinon → cadence = 60 s (par défaut)

#### Sécurité timeout côté TB

Rule chain dédiée "Live Timeout Sweep" cron 1×/min :

```
[Generator cron */1 * * * *]
    → [Fetch devices with live=true]
    → [Filter liveTs < now - 180000]
    → [Save Attribute SHARED_SCOPE live=false]
```

Garantit le retour à `false` même si le browser se ferme brutalement.

#### Discovery proxy → TB

3 stratégies pour que le proxy maintienne sa connaissance de `live` :

| Stratégie | Latence propagation | Coût proxy→TB | Complexité |
|---|---|---|---|
| (a) GET attributes piggyback sur chaque POST | 1 cycle (~60 s) | 2× requêtes (POST + GET) | Faible |
| (b) Polling périodique GET attributes toutes les N s | N secondes | 1 GET / N s par device | Moyenne |
| (c) WebSocket subscription | instantané | 1 WS persistant par tenant | Élevée |

**Recommandation à la réactivation** : option (a) pour v1 (simple, pas de timer séparé). Migration vers (c) si volume devient un problème.

#### Attributs SHARED_SCOPE introduits

- `live` (boolean)
- `liveTs` (long, epoch ms keep-alive widget MAJ toutes les 60 s)

Tout le reste du contrat v2 actuel n'utilise **aucun** attribut SHARED. Si le mode live est réactivé, ces 2 attributs s'ajoutent.

#### Composants à créer à la réactivation

1. Rule chain "Live Timeout Sweep" (~3-4 nodes : Generator cron + Fetch devices + Filter + Save Attribute)
2. Widget custom JS keep-alive sur les states détail (~30 lignes JS)
3. Logique discovery proxy P7-a (modif binary Rust telemetry-proxy ou wrapper externe)
4. (Optionnel) Extension TB `postTelemetry?withSharedKeys=live` si proxy P7 devient trop coûteux

Sans cette réactivation : cadence 1/min fixe, dashboard rafraîchit toutes les minutes avec le dernier `pac_v2`.

## 12. Risques et mitigations

| Risque | Détection | Mitigation |
|---|---|---|
| Script TBEL crash sur 1 post | Failure queue rule chain | Sortie défaut → drop sample (=1 min de données perdues max) |
| Widget TDUO refactorisé affiche valeurs incohérentes | Visuel dashboard pilote J+1 | Revert widget bundle vers version précédente ; la donnée `pac_v2` reste écrite |
| Firmware nested mal formé en production | Switch détecte HPs mais script échoue ; alarme TB sur Failure queue | OTA revert au firmware précédent sur ce device ; branche flat compat prend le relais automatiquement |
| Attribute_kv str_v > limite | `SELECT max(length(str_v))` régulièrement | Réduire ATTR_PATHS dans le script TBEL, redéployer rule chain à chaud |
| Cron DROP PARTITION échoue (verrou, espace) | `/var/log/tb-ts_kv-drop.log` | Alerte log + tentative manuelle ; impact = on garde 1 année de plus, pas critique |

## 13. Acceptance criteria

Le projet est considéré terminé quand :

- 100 % des devices PAC Hybride du parc envoient en format nested v2 (vérifiable via `SELECT count(*) FROM ts_kv WHERE key = 'pac_v2' GROUP BY entity_id`)
- Pendant la transition (Phase 1+), double écriture flat + json_v `pac_v2` (Option B Section 4). Après Phase 3 widgets refactorisés, plus aucune ligne `ts_kv` flat n'est écrite (hors `evt_*`)
- Les 37 attributs SERVER_SCOPE sont présents sur chaque device (cf. Section 3.6 récap)
- L'automate POSTe au proxy avec body bare contenant `dateTime` en string (pas de `ts` epoch). Le proxy parse `dateTime` et wrap en `{ts, values}` avant forward à TB. Les samples (réception normale ou rejoués après reconnexion TB) apparaissent dans `ts_kv` à leur `ts` d'acquisition d'origine, pas au timestamp de réception réseau
- Le rejeu après reconnexion envoie chaque sample en POST individuel sans batch ni throttle ; toutes les lignes `ts_kv` historiques sont écrites correctement
- Le state `default` et `donnees_HP1` affichent correctement les valeurs depuis `pac_v2` sur les 6 widgets TDUO refactorisés
- Le state `historique` affiche un chart 1 an en < 3 s
- Le script de rotation `tb-ts_kv-drop-old-year.sh` a été testé sur un mois fictif (création + drop manuel d'un partition de test)
- Les 13 alarmes orphelines sont supprimées du device profile

> **Mode live exclu des acceptance criteria** — différé (Section 11.1). Cadence 1/min fixe.

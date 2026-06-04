# Marqueurs visuels de défaut comm PAC sur le widget time-series ECharts

**Date** : 2026-06-02
**Statut** : Design approuvé sections 1-3, fichiers touchés en discussion
**Branche cible** : `yahtec-main`
**Spec liée** : `2026-05-28-payload-v2-pac-hybride-design.md` § 3.5 (flux `evt_*`)

## Contexte

Sur les dashboards Yahtec/TSmart suivant des installations PAC hybride + chaudière, on veut un repère visuel direct sur les courbes time-series indiquant les périodes où une PAC hybride était en défaut de communication (hors ligne). Aujourd'hui, ces périodes ne sont visibles que via le widget `tduo.events_history` (liste tabulaire), ce qui force l'utilisateur à croiser deux widgets pour comprendre pourquoi une courbe a un comportement anormal (ex : la chaudière a pris le relais).

La donnée existe déjà côté télémétrie sous la convention `evt_*` standardisée par la spec payload-v2. Aucune source externe à ajouter.

## Objectif

Étendre le widget générique `time-series-chart` (basé ECharts) avec une nouvelle section de configuration "Marqueurs d'événements" qui dessine des **bandes verticales colorées** (`markArea` ECharts) sur les périodes où la machine est considérée hors ligne, selon **deux sources combinables** :

1. **Mode "evt"** — événement explicite : période entre une apparition `evt_status=1` et sa résolution `evt_status=0`, pour un `(evt_fault, evt_device)` donné. C'est le défaut comm vu par l'automate dispatcher.
2. **Mode "gap"** *(ajouté 2026-06-04 sur demande utilisateur)* — pas de communication détecté côté serveur : périodes où aucune trame n'est reçue pendant plus de `N × pas_attendu_sec` sur une clé télémétrie de référence (typiquement une clé qui devrait être présente à chaque cycle normal, ex : `temp_depart_chaud`). Couvre le cas où la machine est tellement offline qu'elle ne peut même pas envoyer son propre `evt_status=1`.

Les deux modes sont configurables indépendamment sur un même marqueur : laisser `evtFaultCodes: []` désactive le mode "evt", laisser `gapThresholdSec: 0` désactive le mode "gap". Activer les deux fusionne les intervalles (l'union, avec déduplication des chevauchements).

Bénéfice : feature réutilisable sur n'importe quel time-series, pas un widget custom de plus à maintenir.

## Conventions de données (rappel, source : spec payload-v2 § 3.5)

À chaque événement (apparition OU résolution), l'automate envoie un POST télémétrie séparé qui pose ces clés flat sur le device PAC :

| Clé | Sens | Type |
|---|---|---|
| `evt_id` | Timestamp epoch **secondes** (×1000 pour ms) | long |
| `evt_status` | `1` = apparition défaut, `0` = disparition défaut | long |
| `evt_fault` | Code défaut (cf. table `FAULT_LABELS`, 114 codes) | long |
| `evt_device` | ID sous-équipement source (50–55 = PAC Hybride 1 à 6 ; 0–12 = chaudières ; 60–68 = module) | long |
| `evt_type` | Catégorie événement (0/1) | long |
| `evt_date` / `evt_time` | Texte horodaté Europe/Paris (humain) | string |

**Codes "défaut communication" identifiés** (lecture de `FAULT_LABELS` dans le widget `events_history`) :

- **Génériques (codes 15, 29, 38, 39, 40, 88)** — libellé exact `Defaut communication`. C'est la **liste par défaut** retenue pour la pré-configuration des marqueurs de défaut comm PAC hybride.
- **Sous-systèmes (codes 84, 85, 86, 87)** — `Defaut com. pompe / compresseur / gaz G20 / gaz R290`. Plus spécifiques, configurables si besoin métier.

**IDs `evt_device` pour PAC hybride** (source : `DEVICE_LABELS` du widget `events_history`) :

| Valeur `evt_device` | Sous-équipement (DEVICE_LABELS) |
|---|---|
| 50 | PAC Hybride 1 |
| 51 | PAC Hybride 2 |
| 52 | PAC Hybride 3 |
| 53 | PAC Hybride 4 |
| 54 | PAC Hybride 5 |
| 55 | PAC Hybride 6 |

> **Note de clarification** : la spec payload-v2 § 3.5 mentionne aussi `evt_device=50` au sens "dispatcher self". Ce sens **ne s'applique qu'au device dispatcher `heatPumpHybride`** (events `evt_dispatch`, `evt_no_id`, `evt_unknown_id`, `evt_provision` — traces internes du routage). Sur les devices PAC individuels (ex : `2602000001`), `evt_device=50` signifie bien **PAC Hybride 1** comme dans `DEVICE_LABELS`. Le widget time-series étant typiquement configuré sur un device PAC (pas sur le dispatcher), aucune confusion en pratique. Si besoin futur d'afficher des marqueurs sur un dashboard pointant le dispatcher, prévoir une option de remapping.

**Hypothèse sur la datasource** : pour que les marqueurs s'affichent, le widget doit avoir **au moins une datasource pointant sur le device PAC** (qui reçoit les `evt_*` en flat depuis le proxy). C'est le cas par défaut sur les dashboards hybrides existants — le device PAC porte toute la télémétrie de l'installation (PAC + chaudière + module). Si un futur dashboard ne pointe qu'un autre device, l'utilisateur devra ajouter le device PAC comme datasource secondaire (au minimum pour les 4 clés `evt_*`).

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Widget time-series-chart (ECharts)                  │
│                                                     │
│  Settings UI  ──────► EventMarkerGroup[]            │
│       │                                             │
│       ▼                                             │
│  Subscription télémétrie                            │
│   tsKeys += [evt_id, evt_status, evt_fault,         │
│              evt_device]                            │
│       │                                             │
│       ▼                                             │
│  Interval reconstruction  (logique pure JS)         │
│   - filtre par evtDeviceId + evtFaultCodes          │
│   - appariement apparition→résolution               │
│   - lookback si bande ouverte au début de fenêtre   │
│       │                                             │
│       ▼                                             │
│  Injection ECharts                                  │
│   - série invisible portant un markArea par groupe  │
│   - color / opacity / decal (pattern)               │
└─────────────────────────────────────────────────────┘
```

## Section 1 — Configuration utilisateur (settings widget)

Nouvelle section *« Marqueurs d'événements »* dans le formulaire de settings du widget, après la section "Thresholds".

Interface TypeScript ajoutée à `time-series-chart.models.ts` :

```ts
export interface TimeSeriesChartEventMarker {
  label: string;              // ex : "PAC1 hors ligne"
  // Mode "evt" — désactivé si evtFaultCodes vide
  evtFaultCodes: number[];    // codes evt_fault à matcher
  evtDeviceId: number;        // valeur evt_device (50..55 pour PAC Hybride 1..6)
  // Mode "gap" — désactivé si gapThresholdSec = 0
  gapThresholdSec: number;    // seuil de gap en secondes (0 = pas de détection gap)
  gapReferenceKey: string;    // nom de la clé télémétrie de référence pour détecter les gaps
  // Style commun
  color: string | 'auto';     // 'auto' = couleur de la datasource dont la clé contient le préfixe matché
  opacity: number;            // 0..1, défaut 0.15
  pattern: 'solid' | 'striped';
}

// Ajout au type existant TimeSeriesChartSettings :
//   eventMarkers: TimeSeriesChartEventMarker[];   // défaut: []
```

Mode `color: 'auto'` : à la résolution, le widget cherche dans ses datasources une clé dont le nom contient l'index PAC (ex : `evtDeviceId=50` → cherche `PAC1` dans `pac1_temp`, `PAC1.temp`, etc., insensible à la casse). Si trouvée, reprend la couleur de la courbe. Sinon fallback gris `#888888`.

UI du formulaire :
- Table éditable (ajout / suppression de lignes)
- Color-picker pour `color` (avec toggle "Auto")
- Multi-select de `evtFaultCodes` (idéalement avec autocomplétion sur les libellés de `FAULT_LABELS` — sinon saisie libre numérique acceptable en v1)
- Dropdown ou input numérique pour `evtDeviceId`
- Slider `opacity` (0.05 à 0.5)
- Toggle `pattern`

## Section 2 — Récupération des données

### Subscription étendue

Au moment où le widget construit sa subscription `EntityDataApi.subscribeForEntityData`, on **ajoute** automatiquement les 4 clés `evt_id`, `evt_status`, `evt_fault`, `evt_device` aux `tsKeys` demandées sur l'entité du widget. Aggregation = `NONE`, même fenêtre temps que le graphe principal.

Pas d'endpoint nouveau, pas de modification backend.

### Reconstruction des intervalles — mode "evt"

Logique pure JS dans un module à part (testable sans ECharts ni Angular) :

```
Entrée : 
  - points = liste de tuples { ts, evt_id, evt_status, evt_fault, evt_device }
            (tous récupérés de la subscription, sur la fenêtre du widget)
  - group  = { evtDeviceId, evtFaultCodes }

Algorithme :
  1. Filtrer points où evt_device == group.evtDeviceId 
                    && evt_fault ∈ group.evtFaultCodes
  2. Pour chaque point retenu, ts_ms = evt_id * 1000 si présent, 
     sinon ts du point lui-même (fallback robuste).
  3. Trier par ts_ms ascendant.
  4. Apparier : parcourir la liste, on maintient un état "défaut ouvert ?" :
       - voir status=1 alors qu'aucun défaut ouvert → ouvrir un intervalle 
         { start: ts_ms, end: null }
       - voir status=0 alors qu'un défaut est ouvert → fermer l'intervalle 
         (end = ts_ms)
       - voir status=1 alors qu'un défaut déjà ouvert → ignorer (doublon)
       - voir status=0 alors qu'aucun défaut ouvert → cas "résolu sans 
         apparition vue dans la fenêtre" : déclenche le lookback (voir 5)
  5. Lookback : si un status=0 orphelin est rencontré et qu'aucun status=1 
     n'a été vu avant lui dans la fenêtre, on émet UN seul appel HTTP 
     timeseries supplémentaire :
        GET /api/plugins/telemetry/DEVICE/{entityId}/values/timeseries
            ?keys=evt_id,evt_status,evt_fault,evt_device
            &endTs=fenêtre.startTs
            &limit=20      ← suffisant pour trouver l'apparition correspondante
     Le widget filtre la réponse pour trouver le dernier status=1 
     correspondant (evt_device + evt_fault) et utilise son evt_id*1000 
     comme start de la bande.
  6. Si à la fin de la traversée un défaut est resté ouvert (end=null), 
     on le rend comme une bande "ouverte" jusqu'à now() (re-rendue à 
     chaque update du widget).

Sortie : liste d'intervalles { start, end, ongoing: bool }
```

Le lookback **n'est déclenché que si nécessaire** (pas de status=0 orphelin → 0 requête supplémentaire) et **au maximum une fois par groupe par cycle de rendu** pour éviter les rafales.

### Reconstruction des intervalles — mode "gap"

Logique pure JS, fonction séparée :

```
Entrée :
  - refPoints = liste de tuples { ts, value } pour la clé gapReferenceKey
                (sur la fenêtre du widget, aggregation NONE)
  - gapThresholdSec : seuil en secondes
  - windowStart, windowEnd : bornes de la fenêtre du widget
  - now : timestamp courant (pour la borne ouverte)

Algorithme :
  1. Si refPoints est vide ET la fenêtre n'est pas dans le futur :
       => toute la fenêtre est considérée comme un gap unique
          intervals = [{ start: windowStart, end: min(windowEnd, now), ongoing: ... }]
  2. Sinon, trier refPoints par ts ascendant.
  3. Construire la liste des bornes : 
       [windowStart, refPoints[0].ts, refPoints[1].ts, ..., refPoints[N].ts, min(windowEnd, now)]
  4. Pour chaque paire consécutive (a, b) dans cette liste :
       Si (b - a) > gapThresholdSec * 1000 :
         intervals.push({ start: a, end: b, ongoing: (b === now) })
  5. Cas particulier "gap en cours" : si le dernier point est à 
     (now - gapThresholdSec*1000) ou plus ancien, le gap est étendu jusqu'à now.

Sortie : liste d'intervalles { start, end, ongoing }
```

**Fusion mode "evt" + mode "gap"** : si les deux modes sont activés sur le même marqueur, on calcule les deux ensembles d'intervalles indépendamment puis on les **fusionne** :

```
Algorithme de fusion :
  1. Concat les deux listes, trier par start ascendant.
  2. Fold : si intervalle[i].end >= intervalle[i+1].start, fusionner en 
     { start: intervalle[i].start, end: max(intervalle[i].end, intervalle[i+1].end),
       ongoing: intervalle[i].ongoing || intervalle[i+1].ongoing }
  3. Sinon garder séparé.
```

Cela évite les bandes superposées illisibles (un défaut `evt_*` à 10h-11h + un gap télémétrie à 10h30-11h30 → une seule bande 10h-11h30).

### Subscription étendue pour le mode "gap"

Quand un marqueur a `gapThresholdSec > 0` et `gapReferenceKey` non vide, on ajoute aussi cette clé à la subscription. Si la clé est déjà présente dans une datasource du widget (cas typique : c'est une courbe affichée), aucune action — on lit ses points existants. Sinon, on l'ajoute en `hidden: true` comme les `evt_*`.

## Section 3 — Rendu ECharts

Pour chaque `EventMarkerGroup`, on ajoute à l'option ECharts :

```js
{
  type: 'line',
  name: group.label,
  data: [],                 // pas de points : la série n'existe que comme support du markArea
  showSymbol: false,
  silent: true,             // ne pas perturber le tooltip principal
  z: 0,                     // fond (sous les courbes data)
  markArea: {
    silent: false,          // tooltip au survol
    itemStyle: {
      color: resolveColor(group),   // 'auto' → couleur de courbe partagée
      opacity: group.opacity,
      ...(group.pattern === 'striped' ? { decal: { symbol: 'rect', dashArrayX: [...] } } : {})
    },
    label: {
      show: false,
      formatter: group.label
    },
    data: intervals.map(iv => [
      { xAxis: iv.start, name: group.label },
      { xAxis: iv.end ?? Date.now() }      // bande ouverte → étendue jusqu'à now
    ])
  }
}
```

Tooltip ECharts natif (au hover sur la bande) affiche `group.label`. Pas besoin de tooltip custom en v1.

La résolution de `color: 'auto'` se fait à l'initialisation : on parcourt `datasources[].dataKeys[]`, on cherche une clé dont le label (insensible à la casse) contient `"PAC" + (evtDeviceId - 49)` (donc PAC1 pour 50, PAC2 pour 51, …). Match → on prend `dataKey.color`. Sinon `#888888`.

## Section 4 — Fichiers touchés

| # | Fichier | Rôle | Modification | Taille estimée |
|---|---|---|---|---|
| 1 | [time-series-chart.models.ts](ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.models.ts) | Modèle de données TypeScript des settings du widget | Nouvelle interface `EventMarkerGroup` + champ `eventMarkerGroups: EventMarkerGroup[]` dans `TimeSeriesChartSettings` + constantes par défaut (codes 15/29/38/39/40/88, devices 50..55). Pas de logique. | ~60 lignes |
| 2 | [time-series-chart-widget.models.ts](ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart-widget.models.ts) | Schéma JSON du formulaire de settings (panneau d'édition du widget) | Déclaration de la section "Marqueurs d'événements" avec ses champs, valeurs par défaut (`eventMarkerGroups: []`). | ~80 lignes |
| 3 | [time-series-chart.ts](ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts) | Moteur de rendu ECharts (settings + données → option ECharts) | (a) Lire `eventMarkerGroups` ; (b) étendre la subscription tsKeys avec `evt_id, evt_status, evt_fault, evt_device` ; (c) appeler le module de reconstruction à chaque update ; (d) gérer le lookback HTTP ; (e) injecter une série invisible avec `markArea` dans l'option ECharts. **Cœur du boulot.** | ~150–200 lignes |
| 4 | Composant Angular du formulaire de settings (à localiser : `time-series-chart-widget-settings.component.ts/html` ou équivalent au même endroit) | UI Angular du panneau de configuration | Rendu de la nouvelle section : `mat-expansion-panel`, table éditable des groupes (add/remove), color-picker avec toggle "Auto", multi-select des codes `evt_fault`, slider opacity, toggle pattern. | ~150 lignes |
| 5 | `event-marker-intervals.spec.ts` *(nouveau, à côté de la logique de reconstruction)* | Tests unitaires de la reconstruction d'intervalles | 6 cas : apparition+résolution simple, deux PAC qui chevauchent, défaut ouvert à `now`, défaut ouvert dès le début de fenêtre (lookback), codes `evt_fault` non concernés filtrés, conversion `evt_id` × 1000. | ~120 lignes |

**Total estimé : ~600 lignes ajoutées, aucun fichier réécrit, aucun fichier supprimé.**

**Hors scope (volontairement) :**
- Pas de nouveau widget custom (on étend `time-series-chart` générique → utilisable partout)
- Pas de modification backend (les `evt_*` arrivent déjà en flat `ts_kv` sur les devices PAC depuis la spec payload-v2)
- Pas de touche au dispatcher ni aux rule chains
- Pas d'autocomplétion `FAULT_LABELS` dans l'UI en v1 (saisie de codes numériques OK) — peut être ajoutée plus tard

## Section 5 — Pré-configuration recommandée

Pour les dashboards PAC hybride existants (à ajouter manuellement à l'édition du widget time-series après merge) :

```json
"eventMarkers": [
  { "label": "PAC1 hors ligne", "evtDeviceId": 50,
    "evtFaultCodes": [15, 29, 38, 39, 40, 88],
    "gapThresholdSec": 600, "gapReferenceKey": "temp_depart_chaud_pac1",
    "color": "auto", "opacity": 0.15, "pattern": "solid" },
  { "label": "PAC2 hors ligne", "evtDeviceId": 51,
    "evtFaultCodes": [15, 29, 38, 39, 40, 88],
    "gapThresholdSec": 600, "gapReferenceKey": "temp_depart_chaud_pac2",
    "color": "auto", "opacity": 0.15, "pattern": "solid" },
  { "label": "PAC3 hors ligne", "evtDeviceId": 52,
    "evtFaultCodes": [15, 29, 38, 39, 40, 88],
    "gapThresholdSec": 600, "gapReferenceKey": "temp_depart_chaud_pac3",
    "color": "auto", "opacity": 0.15, "pattern": "solid" }
]
```

(Étendre PAC4/5/6 → `evt_device` 53/54/55 selon l'installation. Le `gapThresholdSec=600` (10 min) est un défaut prudent — la mémoire projet `project_tduo_payload_architecture.md` indique un cycle live de 1/min, donc un gap > ~5 min serait déjà anormal ; 600s = marge de tolérance contre les latences réseau ou retries proxy.)

Un script de patch (`scripts/tb/widgets/patch-tduo-charts-add-evt-markers.py`) pourra industrialiser l'ajout sur les dashboards existants en prod si nécessaire — **hors scope** du présent design (faisable dans un suivi si demandé).

## Section 6 — Tests

### Tests unitaires (obligatoires avant merge)

Module isolé `event-marker-intervals.ts` (fonction pure `reconstructIntervals(points, group): Interval[]`). Cas couverts :

1. **Cas nominal** : une apparition à t1, une résolution à t2 → un intervalle `[t1, t2]`.
2. **Chevauchement deux PAC** : `evt_device=50` down de t1 à t3, `evt_device=51` down de t2 à t4 → groupes indépendants, 2 intervalles distincts (l'un par groupe).
3. **Défaut ouvert à `now`** : apparition à t1 sans résolution → intervalle `[t1, now]` avec `ongoing=true`.
4. **Lookback** : la fenêtre commence à t10, on voit `evt_status=0` à t12 sans apparition antérieure dans la fenêtre → l'appel mock lookback rend une apparition à t5 → intervalle `[t5, t12]`.
5. **Codes filtrés** : la liste d'entrée contient un événement avec `evt_fault=99` (non listé dans `evtFaultCodes`) → ignoré.
6. **Conversion `evt_id`** : `evt_id=1717200000` (epoch secondes) doit être interprété comme `1717200000000` ms (instant identique au timestamp du point pour vérification).

### Vérification manuelle (avant déploiement prod)

- Charger un dashboard de test (clone d'un dashboard PAC hybride existant), ajouter manuellement les 3 groupes pré-config, choisir une période où on sait qu'une PAC a été en défaut comm (croiser avec le widget `events_history`).
- Vérifier : bande visible, couleur cohérente avec la courbe PAC1, tooltip = label correct, bande s'étend correctement (pas de gap, pas de chevauchement parasite).
- Tester le mode `auto` color : changer la couleur d'une courbe PAC dans les datasources, vérifier que la bande suit.
- Tester avec 0 défaut sur la fenêtre : rien ne doit s'afficher, aucune erreur console.
- Tester avec un défaut en cours : bande s'étend jusqu'à `now`, mise à jour cohérente quand un nouveau point arrive en live.

## Section 7 — Risques et inconnues

| Risque | Mitigation |
|---|---|
| Volume des `evt_*` sur fenêtres longues | Les `evt_*` sont sparse (POST seulement à apparition/résolution), pas de problème de volume. Aucune mesure nécessaire en v1. |
| Conflit avec d'autres `markArea` (thresholds existants) | ECharts supporte plusieurs séries avec `markArea` empilées. `z: 0` garantit qu'on est en fond. À vérifier visuellement en test manuel. |
| Codes `evt_fault` à 0 ou défauts non liés à la communication | L'utilisateur configure `evtFaultCodes` explicitement → pas de risque de marquage parasite tant que la config est correcte. La liste par défaut documentée (15/29/38/39/40/88) doit être validée par Julien sur 1-2 installations test avant généralisation. |
| Couleur `auto` ne matche aucune courbe | Fallback gris `#888888` documenté, aucune erreur visible. |
| `evt_id` absent dans certaines lignes anciennes | Fallback sur `ts` du point lui-même (cf. algo § 2). Documenté. |
| Composant Angular du formulaire de settings non localisé précisément avant implémentation | À identifier à la première étape du plan d'implémentation (avant écriture de code UI). Risque de scope = faible (le fichier existe forcément, c'est juste un Read à faire). |

## Section 8 — Décisions hors scope (à traiter ailleurs si besoin)

- Script Python `patch-tduo-charts-add-evt-markers.py` pour ajouter automatiquement les `eventMarkerGroups` aux widgets time-series déjà déployés en prod (analogue à `patch-events-history-resolution-col.py`). Délivrable potentiel d'un suivi.
- Autocomplétion `FAULT_LABELS` dans l'UI du formulaire (avec libellés humains à côté des codes). Confort UI, peut être ajouté en v2.
- Notification temps-réel "PAC offline depuis Xmn" sur le dashboard (toast / banner). Concept distinct, pas dans ce scope.

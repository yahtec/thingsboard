# Marqueurs visuels de défaut comm PAC — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une section "Marqueurs d'événements" au widget time-series ECharts qui dessine des bandes `markArea` colorées sur les périodes où une PAC hybride est en défaut de communication, reconstruites depuis les clés télémétrie `evt_status`/`evt_fault`/`evt_device`/`evt_id` déjà postées sur le device PAC.

**Architecture:** Extension du widget générique `time-series-chart` (3 fichiers core + 1 composant Angular de settings + 1 module pur). La logique de reconstruction d'intervalles est isolée dans un module pur testable, indépendant d'ECharts et d'Angular. La couleur "auto" résout via les datasources existantes du widget. Lookback HTTP via l'API timeseries native ThingsBoard.

**Tech Stack:** TypeScript 5.x, Angular 20.3, ECharts 5.5.2-TB, Reactive Forms, RxJS, Material Angular 20.2

**Spec source:** [docs/superpowers/specs/2026-06-02-comm-fault-markers-design.md](../specs/2026-06-02-comm-fault-markers-design.md)

---

## Structure des fichiers

| Statut | Fichier | Responsabilité |
|---|---|---|
| **Create** | `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts` | Module pur : reconstruction d'intervalles `start → end` depuis points télémétrie + résolution couleur auto |
| **Create** | `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts` | Tests unitaires (Jasmine, 6 cas) du module pur |
| **Modify** | `ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.models.ts` | Interface `TimeSeriesChartEventMarker` + champ `eventMarkers` dans `TimeSeriesChartSettings` + constantes par défaut |
| **Modify** | `ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts` | `setupEventMarkers()`, subscription `evt_*`, génération markArea, lookback HTTP |
| **Create** | `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.ts` | Composant Angular liste éditable des groupes |
| **Create** | `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.html` | Template UI (table add/remove + champs) |
| **Create** | `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.scss` | Styles locaux du panel |
| **Modify** | `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-widget-settings.component.ts` | FormControl `eventMarkers` |
| **Modify** | `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-widget-settings.component.html` | Insertion du composant `<tb-time-series-chart-event-markers-panel>` |
| **Modify** | `ui-ngx/src/app/modules/home/components/widget/widget-components.module.ts` (à vérifier — module qui déclare le settings panel) | Déclaration du nouveau composant |

**Total estimé : 3 fichiers créés (.ts + .spec.ts + composant trio html/ts/scss) + 4 fichiers modifiés**

---

## Notes de conventions (issues du repo)

- Code style : 4 espaces, single quotes, `import` ordonnés par groupe (Angular > rxjs > third-party > app)
- Tous les fichiers commencent par le bloc license header Apache 2.0 (cf. autres fichiers `chart/*.ts`)
- Tests : convention Jasmine (`describe`/`it`/`expect`), exécutables via `npx ng test` (Karma déjà configuré par Angular CLI)
- Commit messages : style conventionnel observé sur `yahtec-main` (ex : `feat(ui-ngx): ...`, `chore: ...`)
- Pas d'emojis dans le code ou les commits
- Branche cible : `yahtec-main` (un commit par task, push à la fin uniquement sur demande)

---

### Task 1 : Module pur de reconstruction des intervalles (TDD)

**Files:**
- Create: `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts`
- Test: `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts`

- [ ] **Step 1.1 : Créer le fichier de tests (red phase)**

Crée `event-marker-intervals.spec.ts` avec le contenu suivant. Header license Apache 2.0 (copier des autres `.spec.ts` du repo si besoin).

```ts
import {
  reconstructIntervals,
  EventMarkerGroupFilter,
  EventPoint,
  ReconstructedInterval
} from './event-marker-intervals';

const PAC1_COMM: EventMarkerGroupFilter = {
  evtDeviceId: 50,
  evtFaultCodes: [15, 29, 38, 39, 40, 88]
};
const PAC2_COMM: EventMarkerGroupFilter = {
  evtDeviceId: 51,
  evtFaultCodes: [15, 29, 38, 39, 40, 88]
};

function pt(ts: number, evt_id: number, evt_status: number, evt_fault: number, evt_device: number): EventPoint {
  return { ts, evt_id, evt_status, evt_fault, evt_device };
}

describe('reconstructIntervals', () => {

  it('nominal: une apparition + une résolution → un intervalle [start, end]', () => {
    const points = [
      pt(1000, 1, 1, 15, 50),
      pt(2000, 2, 0, 15, 50)
    ];
    const out = reconstructIntervals(points, PAC1_COMM, { now: 5000 });
    expect(out.length).toBe(1);
    expect(out[0]).toEqual({ start: 1000, end: 2000, ongoing: false });
  });

  it('deux PAC distinctes : groupes indépendants, pas de mélange', () => {
    const points = [
      pt(1000, 1, 1, 15, 50),
      pt(1500, 1, 1, 29, 51),
      pt(2000, 2, 0, 15, 50),
      pt(3000, 3, 0, 29, 51)
    ];
    const out1 = reconstructIntervals(points, PAC1_COMM, { now: 5000 });
    const out2 = reconstructIntervals(points, PAC2_COMM, { now: 5000 });
    expect(out1).toEqual([{ start: 1000, end: 2000, ongoing: false }]);
    expect(out2).toEqual([{ start: 1500, end: 3000, ongoing: false }]);
  });

  it('défaut ouvert à now : intervalle [start, now] avec ongoing=true', () => {
    const points = [pt(1000, 1, 1, 15, 50)];
    const out = reconstructIntervals(points, PAC1_COMM, { now: 5000 });
    expect(out).toEqual([{ start: 1000, end: 5000, ongoing: true }]);
  });

  it('codes evt_fault hors liste → ignorés', () => {
    const points = [
      pt(1000, 1, 1, 99, 50),
      pt(2000, 2, 0, 99, 50)
    ];
    const out = reconstructIntervals(points, PAC1_COMM, { now: 5000 });
    expect(out).toEqual([]);
  });

  it('conversion evt_id epoch secondes → ms', () => {
    const points = [
      pt(0, 1717200000, 1, 15, 50),
      pt(0, 1717200060, 0, 15, 50)
    ];
    const out = reconstructIntervals(points, PAC1_COMM, { now: 1717300000000 });
    expect(out[0].start).toBe(1717200000 * 1000);
    expect(out[0].end).toBe(1717200060 * 1000);
  });

  it('fallback ts si evt_id absent ou 0', () => {
    const points = [
      pt(1234567000, 0, 1, 15, 50),
      pt(1234568000, 0, 0, 15, 50)
    ];
    const out = reconstructIntervals(points, PAC1_COMM, { now: 1234600000 });
    expect(out[0].start).toBe(1234567000);
    expect(out[0].end).toBe(1234568000);
  });

  it('status=0 orphelin (sans apparition vue) → signalé pour lookback', () => {
    const points = [pt(2000, 2, 0, 15, 50)];
    const collected: number[] = [];
    const out = reconstructIntervals(points, PAC1_COMM, {
      now: 5000,
      onOrphanResolution: (ts) => collected.push(ts)
    });
    expect(out).toEqual([]);
    expect(collected).toEqual([2000]);
  });

  it('status=1 dupliqué pendant un défaut déjà ouvert → ignoré', () => {
    const points = [
      pt(1000, 1, 1, 15, 50),
      pt(1500, 1, 1, 15, 50),
      pt(2000, 2, 0, 15, 50)
    ];
    const out = reconstructIntervals(points, PAC1_COMM, { now: 5000 });
    expect(out).toEqual([{ start: 1000, end: 2000, ongoing: false }]);
  });
});
```

- [ ] **Step 1.2 : Exécuter les tests, vérifier qu'ils échouent**

Run: `cd ui-ngx && npx ng test --include=src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts --watch=false --browsers=ChromeHeadless`

Expected: FAIL avec `Cannot find module './event-marker-intervals'` (le fichier d'implémentation n'existe pas encore).

> Si Karma n'est pas configuré dans ce repo (test command absent de package.json), exécuter à la place une vérification de compilation : `cd ui-ngx && npx tsc --noEmit src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts` → erreur attendue "Cannot find module".

- [ ] **Step 1.3 : Créer le module d'implémentation**

Crée `event-marker-intervals.ts` avec le header license Apache 2.0 puis :

```ts
export interface EventPoint {
  ts: number;          // timestamp du point télémétrie (ms)
  evt_id: number;      // epoch secondes selon convention payload-v2 § 3.5
  evt_status: number;  // 1=apparition, 0=disparition
  evt_fault: number;   // code défaut
  evt_device: number;  // ID sous-équipement (50-55 = PAC Hybride 1-6)
}

export interface EventMarkerGroupFilter {
  evtDeviceId: number;
  evtFaultCodes: number[];
}

export interface ReconstructedInterval {
  start: number;
  end: number;
  ongoing: boolean;
}

export interface ReconstructOptions {
  now: number;
  onOrphanResolution?: (resolutionTs: number) => void;
}

export function reconstructIntervals(
  points: EventPoint[],
  filter: EventMarkerGroupFilter,
  opts: ReconstructOptions
): ReconstructedInterval[] {
  const codeSet = new Set(filter.evtFaultCodes);

  const filtered = points
    .filter(p => p.evt_device === filter.evtDeviceId && codeSet.has(p.evt_fault))
    .map(p => ({
      ts: (p.evt_id && p.evt_id > 0) ? p.evt_id * 1000 : p.ts,
      status: p.evt_status
    }))
    .sort((a, b) => a.ts - b.ts);

  const intervals: ReconstructedInterval[] = [];
  let openStart: number | null = null;

  for (const ev of filtered) {
    if (ev.status === 1) {
      if (openStart === null) {
        openStart = ev.ts;
      }
      // status=1 alors qu'un défaut est déjà ouvert → doublon, ignoré
    } else if (ev.status === 0) {
      if (openStart !== null) {
        intervals.push({ start: openStart, end: ev.ts, ongoing: false });
        openStart = null;
      } else {
        // résolution orpheline → signaler pour lookback
        opts.onOrphanResolution?.(ev.ts);
      }
    }
  }

  if (openStart !== null) {
    intervals.push({ start: openStart, end: opts.now, ongoing: true });
  }

  return intervals;
}
```

- [ ] **Step 1.4 : Exécuter les tests, vérifier qu'ils passent**

Run: même commande qu'au Step 1.2.
Expected: PASS pour les 8 cas.

- [ ] **Step 1.5 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts
git commit -m "feat(ui-ngx/chart): pure module to reconstruct evt_* intervals for time-series markers"
```

---

### Task 2 : Helper de résolution de couleur "auto" (TDD)

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts`
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts`

- [ ] **Step 2.1 : Ajouter les tests pour `resolveMarkerColor`**

Ajoute à la fin de `event-marker-intervals.spec.ts` :

```ts
import { resolveMarkerColor, NamedDataKey } from './event-marker-intervals';

describe('resolveMarkerColor', () => {
  const keys: NamedDataKey[] = [
    { label: 'PAC1.temp', color: '#ff0000' },
    { label: 'PAC2.temp', color: '#00ff00' },
    { label: 'Chaudiere.temp', color: '#0000ff' }
  ];

  it("evtDeviceId=50 → match 'PAC1' → couleur de la courbe correspondante", () => {
    expect(resolveMarkerColor('auto', 50, keys)).toBe('#ff0000');
  });

  it("evtDeviceId=51 → match 'PAC2'", () => {
    expect(resolveMarkerColor('auto', 51, keys)).toBe('#00ff00');
  });

  it('couleur explicite → retournée telle quelle (auto ignoré)', () => {
    expect(resolveMarkerColor('#abcdef', 50, keys)).toBe('#abcdef');
  });

  it("aucun match auto → fallback gris #888888", () => {
    expect(resolveMarkerColor('auto', 55, keys)).toBe('#888888');
  });

  it("match insensible à la casse", () => {
    const lowerKeys: NamedDataKey[] = [{ label: 'pac1.t', color: '#123456' }];
    expect(resolveMarkerColor('auto', 50, lowerKeys)).toBe('#123456');
  });
});
```

- [ ] **Step 2.2 : Lancer les tests, vérifier que les nouveaux échouent**

Run: même commande qu'au Step 1.2.
Expected: 5 tests `resolveMarkerColor` FAIL avec `resolveMarkerColor is not a function`. Les 8 anciens passent.

- [ ] **Step 2.3 : Ajouter l'implémentation à `event-marker-intervals.ts`**

Ajoute à la fin du fichier :

```ts
export interface NamedDataKey {
  label: string;
  color: string;
}

const AUTO_COLOR_FALLBACK = '#888888';

export function resolveMarkerColor(
  configured: string | 'auto',
  evtDeviceId: number,
  dataKeys: NamedDataKey[]
): string {
  if (configured !== 'auto') {
    return configured;
  }
  const pacIndex = evtDeviceId - 49;
  if (pacIndex < 1) {
    return AUTO_COLOR_FALLBACK;
  }
  const needle = `pac${pacIndex}`;
  const match = dataKeys.find(k => k.label.toLowerCase().includes(needle));
  return match ? match.color : AUTO_COLOR_FALLBACK;
}
```

- [ ] **Step 2.4 : Lancer les tests, vérifier que tout passe**

Expected: 13 tests PASS (8 reconstructIntervals + 5 resolveMarkerColor).

- [ ] **Step 2.5 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts
git commit -m "feat(ui-ngx/chart): resolveMarkerColor helper for auto-color marker bands"
```

---

### Task 2bis : Détection de gap télémétrie + fusion d'intervalles (TDD)

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts`
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts`

- [ ] **Step 2bis.1 : Ajouter les tests pour `reconstructGapIntervals` et `mergeIntervals` (red phase)**

Ajoute à la fin de `event-marker-intervals.spec.ts` :

```ts
import {
  reconstructGapIntervals,
  mergeIntervals,
  ReferencePoint
} from './event-marker-intervals';

describe('reconstructGapIntervals', () => {

  it('aucun gap si tous les points sont espacés en deçà du seuil', () => {
    const refs: ReferencePoint[] = [
      { ts: 1000, value: 1 },
      { ts: 2000, value: 1 },
      { ts: 3000, value: 1 }
    ];
    const out = reconstructGapIntervals(refs, {
      gapThresholdSec: 2, windowStart: 1000, windowEnd: 3000, now: 5000
    });
    expect(out).toEqual([]);
  });

  it('un gap entre deux points si écart > seuil', () => {
    const refs: ReferencePoint[] = [
      { ts: 1000, value: 1 },
      { ts: 6000, value: 1 }
    ];
    const out = reconstructGapIntervals(refs, {
      gapThresholdSec: 2, windowStart: 1000, windowEnd: 6000, now: 10000
    });
    expect(out).toEqual([{ start: 1000, end: 6000, ongoing: false }]);
  });

  it("aucun point sur la fenêtre → la fenêtre entière est un gap", () => {
    const out = reconstructGapIntervals([], {
      gapThresholdSec: 60, windowStart: 1000, windowEnd: 5000, now: 5000
    });
    expect(out).toEqual([{ start: 1000, end: 5000, ongoing: true }]);
  });

  it('gap en cours : dernier point trop ancien par rapport à now', () => {
    const refs: ReferencePoint[] = [{ ts: 1000, value: 1 }];
    const out = reconstructGapIntervals(refs, {
      gapThresholdSec: 2, windowStart: 1000, windowEnd: 10000, now: 10000
    });
    expect(out).toEqual([{ start: 1000, end: 10000, ongoing: true }]);
  });

  it("gap initial : premier point arrive longtemps après windowStart", () => {
    const refs: ReferencePoint[] = [
      { ts: 5000, value: 1 },
      { ts: 6000, value: 1 }
    ];
    const out = reconstructGapIntervals(refs, {
      gapThresholdSec: 2, windowStart: 1000, windowEnd: 6000, now: 6000
    });
    expect(out).toEqual([{ start: 1000, end: 5000, ongoing: false }]);
  });

  it('gapThresholdSec=0 → mode désactivé, jamais de gap', () => {
    const out = reconstructGapIntervals([], {
      gapThresholdSec: 0, windowStart: 1000, windowEnd: 5000, now: 5000
    });
    expect(out).toEqual([]);
  });
});

describe('mergeIntervals', () => {

  it('liste vide → vide', () => {
    expect(mergeIntervals([])).toEqual([]);
  });

  it('intervalles disjoints → conservés tels quels (triés)', () => {
    const out = mergeIntervals([
      { start: 100, end: 200, ongoing: false },
      { start: 50, end: 80, ongoing: false }
    ]);
    expect(out).toEqual([
      { start: 50, end: 80, ongoing: false },
      { start: 100, end: 200, ongoing: false }
    ]);
  });

  it('intervalles chevauchants → fusionnés', () => {
    const out = mergeIntervals([
      { start: 100, end: 200, ongoing: false },
      { start: 150, end: 250, ongoing: false }
    ]);
    expect(out).toEqual([{ start: 100, end: 250, ongoing: false }]);
  });

  it('intervalle ongoing fusionné → reste ongoing', () => {
    const out = mergeIntervals([
      { start: 100, end: 200, ongoing: false },
      { start: 150, end: 300, ongoing: true }
    ]);
    expect(out).toEqual([{ start: 100, end: 300, ongoing: true }]);
  });

  it('chaîne de 3 chevauchants → 1 seul', () => {
    const out = mergeIntervals([
      { start: 100, end: 200, ongoing: false },
      { start: 180, end: 280, ongoing: false },
      { start: 260, end: 350, ongoing: false }
    ]);
    expect(out).toEqual([{ start: 100, end: 350, ongoing: false }]);
  });
});
```

- [ ] **Step 2bis.2 : Lancer les tests, vérifier que les nouveaux échouent**

Run: même commande qu'au Step 1.2.
Expected: 11 nouveaux tests FAIL (`reconstructGapIntervals` / `mergeIntervals` introuvables). Les 13 précédents passent.

- [ ] **Step 2bis.3 : Implémenter `reconstructGapIntervals` et `mergeIntervals`**

Ajoute à la fin de `event-marker-intervals.ts` :

```ts
export interface ReferencePoint {
  ts: number;
  value: number;
}

export interface GapReconstructOptions {
  gapThresholdSec: number;
  windowStart: number;
  windowEnd: number;
  now: number;
}

export function reconstructGapIntervals(
  refs: ReferencePoint[],
  opts: GapReconstructOptions
): ReconstructedInterval[] {
  if (opts.gapThresholdSec <= 0) {
    return [];
  }

  const thresholdMs = opts.gapThresholdSec * 1000;
  const effectiveEnd = Math.min(opts.windowEnd, opts.now);
  const sorted = [...refs].sort((a, b) => a.ts - b.ts);

  if (sorted.length === 0) {
    return [{
      start: opts.windowStart,
      end: effectiveEnd,
      ongoing: effectiveEnd >= opts.now
    }];
  }

  const boundaries: number[] = [opts.windowStart, ...sorted.map(p => p.ts), effectiveEnd];
  const intervals: ReconstructedInterval[] = [];

  for (let i = 0; i < boundaries.length - 1; i++) {
    const a = boundaries[i];
    const b = boundaries[i + 1];
    if (b - a > thresholdMs) {
      intervals.push({
        start: a,
        end: b,
        ongoing: b === opts.now && i === boundaries.length - 2
      });
    }
  }

  return intervals;
}

export function mergeIntervals(intervals: ReconstructedInterval[]): ReconstructedInterval[] {
  if (intervals.length === 0) return [];

  const sorted = [...intervals].sort((a, b) => a.start - b.start);
  const merged: ReconstructedInterval[] = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const last = merged[merged.length - 1];
    const cur = sorted[i];
    if (cur.start <= last.end) {
      merged[merged.length - 1] = {
        start: last.start,
        end: Math.max(last.end, cur.end),
        ongoing: last.ongoing || cur.ongoing
      };
    } else {
      merged.push(cur);
    }
  }

  return merged;
}
```

- [ ] **Step 2bis.4 : Lancer les tests, vérifier que tout passe**

Expected: 24 tests PASS au total (13 existants + 11 nouveaux).

- [ ] **Step 2bis.5 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.ts ui-ngx/src/app/modules/home/components/widget/lib/chart/event-marker-intervals.spec.ts
git commit -m "feat(ui-ngx/chart): gap-based comm fault detection + interval merge for evt+gap union"
```

---

### Task 3 : Interface `TimeSeriesChartEventMarker` + constantes par défaut

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.models.ts`

- [ ] **Step 3.1 : Ajouter l'interface `TimeSeriesChartEventMarker`**

Localiser l'interface `TimeSeriesChartThreshold` (vers ligne 487) — c'est le pattern à suivre. Ajouter **juste après la définition complète de `TimeSeriesChartThreshold` (avant la prochaine `export`)** :

```ts
export interface TimeSeriesChartEventMarker {
  label: string;
  // Mode "evt" — désactivé si evtFaultCodes vide
  evtFaultCodes: number[];
  evtDeviceId: number;
  // Mode "gap" — désactivé si gapThresholdSec = 0
  gapThresholdSec: number;
  gapReferenceKey: string;
  // Style commun
  color: string | 'auto';
  opacity: number;
  pattern: 'solid' | 'striped';
}

export const timeSeriesChartEventMarkerDefaultSettings: TimeSeriesChartEventMarker = {
  label: 'PAC1 hors ligne',
  evtFaultCodes: [15, 29, 38, 39, 40, 88],
  evtDeviceId: 50,
  gapThresholdSec: 600,
  gapReferenceKey: '',
  color: 'auto',
  opacity: 0.15,
  pattern: 'solid'
};

// Reference (FAULT_LABELS / DEVICE_LABELS) — non importée, juste pour traçabilité de la spec.
// Codes "Defaut communication" (génériques) : 15, 29, 38, 39, 40, 88
// Codes "Defaut com. <composant>" (spécifiques) : 84 (pompe), 85 (compresseur), 86 (gaz G20), 87 (gaz R290)
// evt_device PAC Hybride : 50→PAC1, 51→PAC2, 52→PAC3, 53→PAC4, 54→PAC5, 55→PAC6
// Source : spec 2026-06-02-comm-fault-markers-design.md, sections "Conventions" & "Pré-configuration".
```

- [ ] **Step 3.2 : Ajouter le champ `eventMarkers` à `TimeSeriesChartSettings`**

Localiser l'interface `TimeSeriesChartSettings` (ligne 698 selon la cartographie). Ajouter le champ **juste après `thresholds`** :

```ts
export interface TimeSeriesChartSettings extends TimeSeriesChartTooltipWidgetSettings, TimeSeriesChartComparisonSettings {
  thresholds: TimeSeriesChartThreshold[];
  eventMarkers: TimeSeriesChartEventMarker[];   // ← NEW
  darkMode: boolean;
  // ... reste inchangé
```

- [ ] **Step 3.3 : Ajouter la valeur par défaut dans `timeSeriesChartDefaultSettings`**

Localiser `timeSeriesChartDefaultSettings` (vers ligne 713) et ajouter :

```ts
export const timeSeriesChartDefaultSettings: TimeSeriesChartSettings = {
  thresholds: [],
  eventMarkers: [],   // ← NEW
  darkMode: false,
  // ... reste inchangé
```

- [ ] **Step 3.4 : Vérifier la compilation TypeScript**

Run: `cd ui-ngx && npx tsc --noEmit -p tsconfig.json 2>&1 | grep "time-series-chart\.models\|event-marker" || echo "OK no errors"`

Expected: `OK no errors`. Si erreurs, fixer (oubli d'export, doublon, etc.).

- [ ] **Step 3.5 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.models.ts
git commit -m "feat(ui-ngx/chart): TimeSeriesChartEventMarker interface + defaults for comm-fault markers"
```

---

### Task 4 : Composant Angular `tb-time-series-chart-event-markers-panel`

**Files:**
- Create: `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.ts`
- Create: `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.html`
- Create: `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.scss`

> **Note de cohérence avec l'existant** : avant de coder, **lire `time-series-chart-thresholds-panel.component.ts/html`** dans le même répertoire (`settings/chart/`) pour copier exactement le pattern : imports, `@Component` decorator, `ControlValueAccessor` implementation, `propagateChange`, structure de FormArray. Les snippets ci-dessous suivent ce pattern mais le mimétisme exact évite les bugs Angular Reactive Forms.

- [ ] **Step 4.1 : Lire le panel existant des thresholds pour adapter le pattern**

Run: `cat ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-thresholds-panel.component.ts | head -80`

Noter : la classe d'imports, le sélecteur (`tb-...`), le `providers: [...]` pour `NG_VALUE_ACCESSOR`, le `@Input() disabled`, la structure de `writeValue`/`registerOnChange`. À reproduire à l'identique pour le nouveau composant.

- [ ] **Step 4.2 : Créer le composant TypeScript**

Crée `time-series-chart-event-markers-panel.component.ts` avec header Apache 2.0 puis :

```ts
import { Component, forwardRef, Input, OnInit } from '@angular/core';
import {
  ControlValueAccessor,
  NG_VALUE_ACCESSOR,
  UntypedFormArray,
  UntypedFormBuilder,
  UntypedFormGroup,
  Validators
} from '@angular/forms';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import {
  TimeSeriesChartEventMarker,
  timeSeriesChartEventMarkerDefaultSettings
} from '@home/components/widget/lib/chart/time-series-chart.models';

@Component({
  selector: 'tb-time-series-chart-event-markers-panel',
  templateUrl: './time-series-chart-event-markers-panel.component.html',
  styleUrls: ['./time-series-chart-event-markers-panel.component.scss'],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => TimeSeriesChartEventMarkersPanelComponent),
      multi: true
    }
  ],
  standalone: false
})
export class TimeSeriesChartEventMarkersPanelComponent implements OnInit, ControlValueAccessor {

  @Input() disabled = false;

  eventMarkersFormGroup: UntypedFormGroup;

  private propagateChange: (value: TimeSeriesChartEventMarker[]) => void = () => {};
  private destroy$ = new Subject<void>();

  constructor(private fb: UntypedFormBuilder) {}

  ngOnInit(): void {
    this.eventMarkersFormGroup = this.fb.group({
      markers: this.fb.array([])
    });
    this.eventMarkersFormGroup.valueChanges
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        const value = this.markersFormArray.controls.map(c => c.value as TimeSeriesChartEventMarker);
        this.propagateChange(value);
      });
  }

  get markersFormArray(): UntypedFormArray {
    return this.eventMarkersFormGroup.get('markers') as UntypedFormArray;
  }

  registerOnChange(fn: (value: TimeSeriesChartEventMarker[]) => void): void {
    this.propagateChange = fn;
  }

  registerOnTouched(_fn: () => void): void {}

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
    if (isDisabled) {
      this.eventMarkersFormGroup.disable({ emitEvent: false });
    } else {
      this.eventMarkersFormGroup.enable({ emitEvent: false });
    }
  }

  writeValue(value: TimeSeriesChartEventMarker[]): void {
    const safe = Array.isArray(value) ? value : [];
    while (this.markersFormArray.length) {
      this.markersFormArray.removeAt(0, { emitEvent: false });
    }
    safe.forEach(m => this.markersFormArray.push(this.buildMarkerGroup(m), { emitEvent: false }));
  }

  addMarker(): void {
    this.markersFormArray.push(this.buildMarkerGroup({ ...timeSeriesChartEventMarkerDefaultSettings }));
  }

  removeMarker(index: number): void {
    this.markersFormArray.removeAt(index);
  }

  private buildMarkerGroup(m: TimeSeriesChartEventMarker): UntypedFormGroup {
    return this.fb.group({
      label: [m.label, [Validators.required]],
      evtFaultCodes: [m.evtFaultCodes, []],
      evtDeviceId: [m.evtDeviceId, [Validators.required, Validators.min(0)]],
      gapThresholdSec: [m.gapThresholdSec ?? 0, [Validators.required, Validators.min(0)]],
      gapReferenceKey: [m.gapReferenceKey ?? '', []],
      color: [m.color, [Validators.required]],
      opacity: [m.opacity, [Validators.required, Validators.min(0), Validators.max(1)]],
      pattern: [m.pattern, [Validators.required]]
    });
  }

  // ngOnDestroy via destroy$ pattern handled by takeUntil
}
```

- [ ] **Step 4.3 : Créer le template HTML**

Crée `time-series-chart-event-markers-panel.component.html` :

```html
<div class="tb-form-panel no-border no-padding event-markers-panel" [formGroup]="eventMarkersFormGroup">
  <div class="tb-form-panel-title" translate>widgets.time-series-chart.event-markers</div>

  <div class="tb-form-hint" translate>widgets.time-series-chart.event-markers-hint</div>

  <div formArrayName="markers" class="markers-list">
    <div *ngFor="let markerCtrl of markersFormArray.controls; let i = index"
         [formGroupName]="i"
         class="marker-row">
      <div class="marker-row-header">
        <span class="marker-index">#{{ i + 1 }}</span>
        <button mat-icon-button type="button"
                [disabled]="disabled"
                (click)="removeMarker(i)"
                matTooltip="{{ 'action.remove' | translate }}">
          <mat-icon>delete</mat-icon>
        </button>
      </div>

      <div class="marker-row-fields">
        <mat-form-field appearance="outline" class="flex-1">
          <mat-label translate>widgets.time-series-chart.event-marker-label</mat-label>
          <input matInput formControlName="label" required>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-100">
          <mat-label translate>widgets.time-series-chart.event-marker-device-id</mat-label>
          <input matInput type="number" formControlName="evtDeviceId" required>
          <mat-hint>50=PAC1, 51=PAC2, 52=PAC3, 53=PAC4, 54=PAC5, 55=PAC6</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="flex-1">
          <mat-label translate>widgets.time-series-chart.event-marker-fault-codes</mat-label>
          <input matInput formControlName="evtFaultCodes"
                 placeholder="15, 29, 38, 39, 40, 88">
          <mat-hint translate>widgets.time-series-chart.event-marker-fault-codes-hint</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-120">
          <mat-label translate>widgets.time-series-chart.event-marker-gap-threshold</mat-label>
          <input matInput type="number" min="0" step="30"
                 formControlName="gapThresholdSec">
          <mat-hint translate>widgets.time-series-chart.event-marker-gap-threshold-hint</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="flex-1">
          <mat-label translate>widgets.time-series-chart.event-marker-gap-reference-key</mat-label>
          <input matInput formControlName="gapReferenceKey"
                 placeholder="temp_depart_chaud_pac1">
          <mat-hint translate>widgets.time-series-chart.event-marker-gap-reference-key-hint</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-150">
          <mat-label translate>widgets.time-series-chart.event-marker-color</mat-label>
          <input matInput formControlName="color" required
                 placeholder="auto ou #RRGGBB">
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-100">
          <mat-label translate>widgets.time-series-chart.event-marker-opacity</mat-label>
          <input matInput type="number" step="0.05" min="0" max="1"
                 formControlName="opacity" required>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-120">
          <mat-label translate>widgets.time-series-chart.event-marker-pattern</mat-label>
          <mat-select formControlName="pattern" required>
            <mat-option value="solid">solid</mat-option>
            <mat-option value="striped">striped</mat-option>
          </mat-select>
        </mat-form-field>
      </div>
    </div>

    <button mat-stroked-button type="button" color="primary"
            [disabled]="disabled"
            (click)="addMarker()">
      <mat-icon>add</mat-icon>
      <span translate>widgets.time-series-chart.add-event-marker</span>
    </button>
  </div>
</div>
```

> **Note `evtFaultCodes`** : en v1 on stocke un `number[]` mais l'input texte le présente comme CSV. Un transform input/output sera ajouté plus tard pour passer `string → number[]`. Pour l'instant, accepter une saisie sous forme de tableau JSON littéral (ex : `[15,29,38,39,40,88]`) si Angular le parse mal — alternative : ajouter un `parseCodesString()` dans le composant TS, à ajouter au Step 4.4.

- [ ] **Step 4.4 : Ajouter le parsing CSV pour evtFaultCodes**

Modifier `time-series-chart-event-markers-panel.component.ts` — dans la méthode `buildMarkerGroup`, remplacer la ligne `evtFaultCodes` par :

```ts
      evtFaultCodes: [Array.isArray(m.evtFaultCodes) ? m.evtFaultCodes.join(',') : m.evtFaultCodes,
                      [Validators.required]],
```

Et dans la méthode `valueChanges` de `ngOnInit`, ajuster la transformation :

```ts
    this.eventMarkersFormGroup.valueChanges
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        const value = this.markersFormArray.controls.map(c => {
          const raw = c.value as any;
          const codes: number[] = typeof raw.evtFaultCodes === 'string'
            ? raw.evtFaultCodes.split(',').map((s: string) => parseInt(s.trim(), 10)).filter((n: number) => !isNaN(n))
            : (raw.evtFaultCodes || []);
          return { ...raw, evtFaultCodes: codes } as TimeSeriesChartEventMarker;
        });
        this.propagateChange(value);
      });
```

- [ ] **Step 4.5 : Créer le SCSS**

Crée `time-series-chart-event-markers-panel.component.scss` :

```scss
:host {
  display: block;
}

.event-markers-panel {
  .markers-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .marker-row {
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 4px;
    padding: 8px 12px;
    background: rgba(0, 0, 0, 0.02);
  }

  .marker-row-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;

    .marker-index {
      font-weight: 600;
      color: rgba(0, 0, 0, 0.6);
    }
  }

  .marker-row-fields {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: flex-start;

    .flex-1 { flex: 1 1 160px; min-width: 160px; }
    .w-100 { width: 110px; }
    .w-120 { width: 130px; }
    .w-150 { width: 160px; }
  }
}
```

- [ ] **Step 4.6 : Déclarer le composant dans le module Angular approprié**

Identifier le module qui déclare `TimeSeriesChartThresholdsPanelComponent`. Run :

```bash
grep -rn "TimeSeriesChartThresholdsPanelComponent" ui-ngx/src/app --include="*.module.ts" | head
```

Dans le ou les modules trouvés, **ajouter au même endroit** :
- import : `import { TimeSeriesChartEventMarkersPanelComponent } from '@home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component';`
- dans `declarations: [...]` : `TimeSeriesChartEventMarkersPanelComponent,`
- dans `exports: [...]` (s'il y est) : idem

- [ ] **Step 4.7 : Ajouter les traductions FR/EN**

Localiser le fichier de traductions principal : `ui-ngx/src/assets/locale/locale.constant-fr_FR.json` et son équivalent `en_US`. Trouver la section `"widgets": { "time-series-chart": { ... } }` et ajouter sous cette clé :

```json
"event-markers": "Marqueurs d'événements",
"event-markers-hint": "Bandes colorées sur la courbe indiquant les périodes où une PAC est en défaut de communication (reconstruites depuis les clés evt_* du device).",
"event-marker-label": "Libellé",
"event-marker-device-id": "evt_device (PAC)",
"event-marker-fault-codes": "Codes evt_fault (séparés par virgule)",
"event-marker-fault-codes-hint": "Ex : 15, 29, 38, 39, 40, 88 (Defaut communication)",
"event-marker-color": "Couleur",
"event-marker-opacity": "Opacité",
"event-marker-pattern": "Motif",
"add-event-marker": "Ajouter un marqueur"
```

Équivalent EN dans `locale.constant-en_US.json` :

```json
"event-markers": "Event markers",
"event-markers-hint": "Colored bands on the chart indicating periods when a PAC is in communication fault (reconstructed from evt_* keys on the device, optionally combined with telemetry gap detection).",
"event-marker-label": "Label",
"event-marker-device-id": "evt_device (PAC)",
"event-marker-fault-codes": "evt_fault codes (comma-separated)",
"event-marker-fault-codes-hint": "Ex: 15, 29, 38, 39, 40, 88 (Defaut communication). Empty disables evt mode.",
"event-marker-gap-threshold": "Gap (s)",
"event-marker-gap-threshold-hint": "0 disables gap detection. Recommended: 600 (10 min).",
"event-marker-gap-reference-key": "Reference key (gap)",
"event-marker-gap-reference-key-hint": "Telemetry key whose missing samples indicate offline state",
"event-marker-color": "Color",
"event-marker-opacity": "Opacity",
"event-marker-pattern": "Pattern",
"add-event-marker": "Add marker"
```

Et le FR `locale.constant-fr_FR.json` complété avec les 3 nouvelles clés :

```json
"event-markers-hint": "Bandes colorées sur la courbe indiquant les périodes où une PAC est en défaut de communication (reconstruites depuis les clés evt_* du device, et/ou détection de gap télémétrie).",
"event-marker-fault-codes-hint": "Ex : 15, 29, 38, 39, 40, 88 (Defaut communication). Vide pour désactiver le mode evt.",
"event-marker-gap-threshold": "Gap (s)",
"event-marker-gap-threshold-hint": "0 = désactivé. Recommandé : 600 (10 min).",
"event-marker-gap-reference-key": "Clé de référence (gap)",
"event-marker-gap-reference-key-hint": "Clé télémétrie dont l'absence indique un état offline"
```

- [ ] **Step 4.8 : Vérifier la compilation Angular**

Run: `cd ui-ngx && npx ng build --configuration development 2>&1 | tail -40`

Expected: build réussi, pas d'erreur Angular template ou TS sur le nouveau composant.

> Si l'erreur "module not found" ou "component not declared" surgit, repasser au Step 4.6 et vérifier l'import dans le bon module.

- [ ] **Step 4.9 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-event-markers-panel.component.* ui-ngx/src/app/modules/home/components/widget/widget-components.module.ts ui-ngx/src/assets/locale/locale.constant-*.json
git commit -m "feat(ui-ngx/chart): event-markers settings panel component with CSV codes input"
```

---

### Task 5 : Intégration du panel dans le settings widget parent

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-widget-settings.component.ts`
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-widget-settings.component.html`

- [ ] **Step 5.1 : Ajouter le FormControl `eventMarkers` dans le composant TS**

Localiser `time-series-chart-widget-settings.component.ts` vers ligne 135 (déclaration de la FormGroup, ligne avec `thresholds: [settings.thresholds, []],`). Ajouter **juste après** :

```ts
      thresholds: [settings.thresholds, []],
      eventMarkers: [settings.eventMarkers, []],   // ← NEW
      dataZoom: [settings.dataZoom, []],
```

- [ ] **Step 5.2 : Ajouter le composant panel dans le HTML**

Localiser dans `time-series-chart-widget-settings.component.html` la section thresholds (vers ligne 72-80, `<tb-time-series-chart-thresholds-panel ...>`). Ajouter **juste après la fermeture `</tb-time-series-chart-thresholds-panel>`** :

```html
</tb-time-series-chart-thresholds-panel>

<tb-time-series-chart-event-markers-panel
    formControlName="eventMarkers">
</tb-time-series-chart-event-markers-panel>
```

(Pas besoin des `aliasController`/`datasource` puisque le panel v1 ne lit pas de datasources externes — il édite uniquement la liste de groupes via inputs scalaires.)

- [ ] **Step 5.3 : Build & vérification rendu UI**

Run: `cd ui-ngx && npx ng build --configuration development 2>&1 | tail -20`

Expected: build OK.

Ensuite, démarrer le dev server : `cd ui-ngx && npm start` (long, en background). Ouvrir un dashboard utilisant un widget time-series, éditer le widget, ouvrir l'onglet "Settings". La section "Marqueurs d'événements" doit apparaître. Cliquer "Ajouter un marqueur" → une ligne avec les valeurs par défaut (label "PAC1 hors ligne", evtDeviceId 50, codes "15,29,38,39,40,88", color "auto", opacity 0.15, pattern "solid"). Pouvoir supprimer la ligne.

**À ce stade le widget ne fait rien de visible sur la courbe — c'est normal.** L'intégration ECharts vient aux Tasks 6-8.

- [ ] **Step 5.4 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-widget-settings.component.ts ui-ngx/src/app/modules/home/components/widget/lib/settings/chart/time-series-chart-widget-settings.component.html
git commit -m "feat(ui-ngx/chart): wire event-markers panel into time-series widget settings form"
```

---

### Task 6 : Méthode `setupEventMarkers()` + subscription télémétrie `evt_*`

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts`

- [ ] **Step 6.1 : Ajouter les imports en tête de fichier**

Ajouter aux imports existants (groupes Angular/rxjs/app séparés) :

```ts
import {
  reconstructIntervals,
  reconstructGapIntervals,
  mergeIntervals,
  resolveMarkerColor,
  EventPoint,
  EventMarkerGroupFilter,
  NamedDataKey,
  ReconstructedInterval,
  ReferencePoint
} from './event-marker-intervals';
import { TimeSeriesChartEventMarker } from './time-series-chart.models';
```

(`TimeSeriesChartEventMarker` peut déjà être exporté depuis `time-series-chart.models` — vérifier qu'il est dans le bloc d'imports depuis ce fichier et l'ajouter si manquant.)

- [ ] **Step 6.2 : Ajouter le state interne pour les event markers**

Localiser la zone des champs privés de la classe `TbTimeSeriesChart` (chercher `private dataItems` ou `private thresholdItems`). Ajouter à côté :

```ts
  private eventMarkerItems: Array<{
    config: TimeSeriesChartEventMarker;
    points: EventPoint[];
    intervals: ReconstructedInterval[];
    lookbackInFlight: boolean;
  }> = [];
```

- [ ] **Step 6.3 : Implémenter `setupEventMarkers()`**

Localiser la méthode `setupThresholds()` (~ligne 567). Ajouter **juste après sa fermeture** :

```ts
  private setupEventMarkers(): void {
    this.eventMarkerItems = (this.settings.eventMarkers || []).map(config => ({
      config,
      points: [],
      intervals: [],
      lookbackInFlight: false
    }));

    if (this.eventMarkerItems.length === 0) {
      return;
    }

    // Étend la subscription télémétrie principale avec les 4 clés evt_*
    // et les gapReferenceKey distinctes utilisées par les markers configurés.
    // Pattern : on parcourt les datasources existantes du widget et on ajoute
    // les keys manquantes au premier datasource de type entity.
    const evtKeys = ['evt_id', 'evt_status', 'evt_fault', 'evt_device'];
    const ds = this.ctx.datasources && this.ctx.datasources.find(d => d.type === 'entity');
    if (!ds) {
      console.warn('[TimeSeriesChart] eventMarkers configured but no entity datasource — markers will not render');
      return;
    }

    // Active le mode evt seulement si au moins un marker a des codes configurés
    const anyEvtMode = this.eventMarkerItems.some(it => it.config.evtFaultCodes?.length > 0);
    const gapKeys = Array.from(new Set(
      this.eventMarkerItems
        .filter(it => it.config.gapThresholdSec > 0 && it.config.gapReferenceKey)
        .map(it => it.config.gapReferenceKey)
    ));

    const keysToAdd = [...(anyEvtMode ? evtKeys : []), ...gapKeys];
    for (const key of keysToAdd) {
      if (!ds.dataKeys.some(k => k.name === key)) {
        ds.dataKeys.push({
          name: key,
          type: 'timeseries',
          label: key,
          color: 'transparent',
          settings: { hidden: true } as any,
          _hash: Math.random()
        } as any);
      }
    }
  }
```

- [ ] **Step 6.4 : Appeler `setupEventMarkers()` au bon endroit**

Localiser le constructeur ou la méthode d'init principale (probablement appelle `setupData()` puis `setupThresholds()` autour de la ligne 200). Ajouter l'appel :

```ts
    this.setupData();
    this.setupThresholds();
    this.setupEventMarkers();   // ← NEW
```

- [ ] **Step 6.5 : Vérifier la compilation**

Run: `cd ui-ngx && npx ng build --configuration development 2>&1 | tail -20`
Expected: build OK.

> ⚠️ **Point d'attention** : l'API exacte de `ctx.datasources[].dataKeys` peut différer (le `_hash` et le type `DataKey` complet varient selon les versions TB). Si la compilation échoue sur le `push()`, ouvrir `ui-ngx/src/app/shared/models/widget.models.ts` et lire l'interface `DataKey` pour fournir tous les champs requis. Le pattern correct est probablement de cloner un dataKey existant et de remplacer juste `name`/`label`.

- [ ] **Step 6.6 : Vérification manuelle subscription**

Démarrer dev server, ouvrir un dashboard utilisant le widget. Ajouter un marqueur via les settings (cf. Task 5). Sauvegarder le widget. Ouvrir DevTools Network, filtrer sur `subscribeForEntityData` ou `entityData` — la subscription envoyée doit inclure `evt_id, evt_status, evt_fault, evt_device` dans la liste `tsKeyNames`. Si oui : subscription OK. Si non : revoir Step 6.3.

- [ ] **Step 6.7 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts
git commit -m "feat(ui-ngx/chart): setupEventMarkers wires evt_* keys into the widget subscription"
```

---

### Task 7 : Reconstruction d'intervalles + génération du `markArea` ECharts

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts`

- [ ] **Step 7.1 : Implémenter la collecte des points `evt_*` à chaque update**

Localiser la méthode `update()` (vers ligne 240). Ajouter **à la fin** (juste avant le `this.updateSeriesData(updateScale)` final) :

```ts
    this.collectEventMarkerPoints();
    this.reconstructEventMarkerIntervals();
```

Puis ajouter ces deux méthodes privées **dans la classe** (n'importe où après `update()`) :

```ts
  private collectEventMarkerPoints(): void {
    if (this.eventMarkerItems.length === 0) return;

    const evtKeys = ['evt_id', 'evt_status', 'evt_fault', 'evt_device'];
    const dataByKey: Record<string, Array<[number, any]>> = {};
    for (const key of evtKeys) {
      const series = this.ctx.data?.find(d => d.dataKey?.name === key);
      dataByKey[key] = series?.data || [];
    }

    // Toutes les clés evt_* sont postées dans le même message TB, donc même ts.
    // On indexe par ts pour reconstituer les points.
    const byTs: Map<number, Partial<EventPoint>> = new Map();
    for (const key of evtKeys) {
      for (const [ts, val] of dataByKey[key]) {
        const entry = byTs.get(ts) || { ts };
        (entry as any)[key] = Number(val);
        byTs.set(ts, entry);
      }
    }

    const points: EventPoint[] = Array.from(byTs.values())
      .filter(e => e.evt_status !== undefined && e.evt_fault !== undefined && e.evt_device !== undefined)
      .map(e => ({
        ts: e.ts as number,
        evt_id: (e.evt_id as number) || 0,
        evt_status: e.evt_status as number,
        evt_fault: e.evt_fault as number,
        evt_device: e.evt_device as number
      }));

    for (const item of this.eventMarkerItems) {
      item.points = points;
    }
  }

  private reconstructEventMarkerIntervals(): void {
    const now = Date.now();
    const windowStart = this.ctx.defaultSubscription?.timeWindow?.minTime ?? 0;
    const windowEnd = this.ctx.defaultSubscription?.timeWindow?.maxTime ?? now;

    for (const item of this.eventMarkerItems) {
      // Mode evt
      let evtIntervals: ReconstructedInterval[] = [];
      let needLookback = false;
      if ((item.config.evtFaultCodes?.length || 0) > 0) {
        const filter: EventMarkerGroupFilter = {
          evtDeviceId: item.config.evtDeviceId,
          evtFaultCodes: item.config.evtFaultCodes
        };
        evtIntervals = reconstructIntervals(item.points, filter, {
          now,
          onOrphanResolution: () => { needLookback = true; }
        });
      }

      // Mode gap
      let gapIntervals: ReconstructedInterval[] = [];
      if (item.config.gapThresholdSec > 0 && item.config.gapReferenceKey) {
        const refSeries = this.ctx.data?.find(d => d.dataKey?.name === item.config.gapReferenceKey);
        const refs: ReferencePoint[] = (refSeries?.data || []).map(([ts, value]: [number, any]) => ({
          ts, value: Number(value)
        }));
        gapIntervals = reconstructGapIntervals(refs, {
          gapThresholdSec: item.config.gapThresholdSec,
          windowStart,
          windowEnd,
          now
        });
      }

      // Fusion + déduplication
      item.intervals = mergeIntervals([...evtIntervals, ...gapIntervals]);

      if (needLookback && !item.lookbackInFlight) {
        this.triggerLookbackFor(item);   // implémenté en Task 8
      }
    }
  }

  private triggerLookbackFor(_item: typeof this.eventMarkerItems[number]): void {
    // Implémenté en Task 8 — stub vide pour que ça compile.
  }
```

- [ ] **Step 7.2 : Générer le `markArea` ECharts**

Localiser `updateSeries()` (vers ligne 884) ou la fonction `generateChartData()` qu'elle appelle. Ajouter **juste après l'assignment de `this.timeSeriesChartOptions.series`** (au retour de `generateChartData`) :

```ts
    // Append invisible series carrying markArea bands for each event marker group.
    const markerSeries = this.buildEventMarkerSeries();
    if (markerSeries.length) {
      this.timeSeriesChartOptions.series = [
        ...(this.timeSeriesChartOptions.series as any[]),
        ...markerSeries
      ];
    }
```

Puis ajouter la méthode privée `buildEventMarkerSeries()` :

```ts
  private buildEventMarkerSeries(): any[] {
    if (this.eventMarkerItems.length === 0) return [];

    const namedKeys: NamedDataKey[] = [];
    for (const ds of this.ctx.datasources || []) {
      for (const dk of (ds.dataKeys || [])) {
        if (dk.color && dk.label) {
          namedKeys.push({ label: dk.label, color: dk.color });
        }
      }
    }

    const now = Date.now();
    return this.eventMarkerItems
      .filter(item => item.intervals.length > 0)
      .map(item => {
        const color = resolveMarkerColor(item.config.color, item.config.evtDeviceId, namedKeys);
        const decal = item.config.pattern === 'striped'
          ? { symbol: 'rect', dashArrayX: [[10, 10]], dashArrayY: [4, 0], rotation: -Math.PI / 4 }
          : null;
        return {
          type: 'line',
          name: item.config.label,
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: [],
          showSymbol: false,
          silent: true,
          z: 0,
          markArea: {
            silent: false,
            itemStyle: {
              color,
              opacity: item.config.opacity,
              ...(decal ? { decal } : {})
            },
            label: { show: false, formatter: item.config.label },
            data: item.intervals.map(iv => [
              { xAxis: iv.start, name: item.config.label },
              { xAxis: iv.ongoing ? now : iv.end }
            ])
          }
        };
      });
  }
```

- [ ] **Step 7.3 : Vérifier la compilation**

Run: `cd ui-ngx && npx ng build --configuration development 2>&1 | tail -20`
Expected: build OK.

- [ ] **Step 7.4 : Vérification visuelle (sans lookback pour l'instant)**

Démarrer dev server. Sur un dashboard PAC hybride réel, charger une fenêtre temps qui contient une apparition ET une résolution de défaut comm dans la même fenêtre (croiser avec le widget `events_history` pour repérer une période sûre). Ajouter un marqueur PAC1 (evtDeviceId=50, codes 15/29/38/39/40/88, color=auto, opacity=0.15). Sauvegarder.

Expected : une bande grisée (ou colorée comme la courbe PAC1 si auto match) s'affiche sur la période du défaut. Hover → tooltip avec le label "PAC1 hors ligne".

Si la bande n'apparaît pas : ouvrir DevTools console et vérifier qu'il n'y a pas d'erreur ECharts ; ajouter un `console.log('intervals', item.intervals)` temporaire dans `reconstructEventMarkerIntervals()` pour confirmer la reconstruction.

- [ ] **Step 7.5 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts
git commit -m "feat(ui-ngx/chart): render evt_* event markers as ECharts markArea bands"
```

---

### Task 8 : Lookback HTTP pour les défauts ouverts au début de fenêtre

**Files:**
- Modify: `ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts`

- [ ] **Step 8.1 : Identifier l'API timeseries à appeler**

Lire dans le code TB existant comment d'autres widgets font un appel ad-hoc `getTimeseries` — chercher `TelemetryWebsocketService` ou `EntityService.getTimeseries`. Run :

```bash
grep -rn "getTimeseries\|/api/plugins/telemetry" ui-ngx/src/app/core/http --include="*.ts" | head -10
```

Identifier la signature exacte (probablement `attributeService.getEntityTimeseries(entityId, keys, ...)` ou `entityService.getTimeseries(...)`).

- [ ] **Step 8.2 : Injecter le service nécessaire**

Le widget context (`this.ctx`) expose typiquement `this.ctx.http` ou des services via `this.ctx.$injector`. Ajouter dans la classe `TbTimeSeriesChart` :

```ts
  // En haut du constructeur, après les autres setup
  private attributeService = this.ctx.$injector.get(AttributeService);
```

(et import : `import { AttributeService } from '@core/http/attribute.service';` — vérifier le nom exact dans le repo).

- [ ] **Step 8.3 : Implémenter `triggerLookbackFor()`**

Remplacer le stub vide :

```ts
  private triggerLookbackFor(item: typeof this.eventMarkerItems[number]): void {
    const entityId = this.ctx.datasources?.[0]?.entity?.id;
    if (!entityId) return;

    const windowStart = this.ctx.defaultSubscription?.timeWindow?.minTime;
    if (!windowStart) return;

    item.lookbackInFlight = true;

    this.attributeService.getEntityTimeseries(
      entityId,
      ['evt_id', 'evt_status', 'evt_fault', 'evt_device'],
      undefined,
      windowStart,
      20,
      'NONE'
    ).subscribe({
      next: (resp: any) => {
        item.lookbackInFlight = false;
        // Construire des EventPoint depuis la réponse lookback
        const byTs: Map<number, Partial<EventPoint>> = new Map();
        for (const key of ['evt_id', 'evt_status', 'evt_fault', 'evt_device']) {
          for (const dp of (resp[key] || [])) {
            const ts = dp.ts;
            const entry = byTs.get(ts) || { ts };
            (entry as any)[key] = Number(dp.value);
            byTs.set(ts, entry);
          }
        }
        const extra: EventPoint[] = Array.from(byTs.values())
          .filter(e => e.evt_status === 1 && e.evt_device === item.config.evtDeviceId
                       && item.config.evtFaultCodes.includes(e.evt_fault as number))
          .map(e => ({
            ts: e.ts as number,
            evt_id: (e.evt_id as number) || 0,
            evt_status: 1,
            evt_fault: e.evt_fault as number,
            evt_device: e.evt_device as number
          }));
        if (extra.length === 0) return;

        // Re-reconstruire avec ces points fusionnés (one-shot, pas de boucle)
        const merged = [...extra, ...item.points];
        item.intervals = reconstructIntervals(merged, {
          evtDeviceId: item.config.evtDeviceId,
          evtFaultCodes: item.config.evtFaultCodes
        }, { now: Date.now() });

        // Re-render
        this.updateSeries();
        this.timeSeriesChart.setOption({ series: this.timeSeriesChartOptions.series });
      },
      error: () => {
        item.lookbackInFlight = false;
      }
    });
  }
```

> **Note signature `getEntityTimeseries`** : adapter exactement à la signature trouvée au Step 8.1. Si la méthode prend `(entityId, keys, startTs, endTs, limit, agg, interval)`, ajuster en conséquence. Le but : un seul appel, `endTs = windowStart` (ou juste avant), `limit ≤ 20`, agg `NONE`.

- [ ] **Step 8.4 : Compilation + vérification visuelle lookback**

Run: `cd ui-ngx && npx ng build --configuration development 2>&1 | tail -20` → OK.

Test manuel : charger une fenêtre **qui commence pendant un défaut comm en cours** (donc on ne voit pas son apparition dans la fenêtre, seulement sa résolution). La bande doit **commencer au bord gauche du graphe** (ou plus tôt si la résolution est aussi hors fenêtre) après que le lookback ait répondu. Inspecter Network : un seul appel `/api/plugins/telemetry/.../timeseries` avec `endTs` ≈ windowStart.

- [ ] **Step 8.5 : Commit**

```bash
git add ui-ngx/src/app/modules/home/components/widget/lib/chart/time-series-chart.ts
git commit -m "feat(ui-ngx/chart): HTTP lookback to recover marker bands opened before window start"
```

---

### Task 9 : Build production + vérification manuelle complète + doc

**Files:**
- Modify: `docs/superpowers/specs/2026-06-02-comm-fault-markers-design.md` (statut → implémenté)
- Optional: `scripts/tb/widgets/patch-time-series-add-evt-markers.py` (à créer si user le demande, hors scope du plan)

- [ ] **Step 9.1 : Build production**

Run: `cd ui-ngx && npm run build:prod 2>&1 | tail -30`
Expected: build prod réussi, pas d'erreur, taille de bundle pas dramatiquement augmentée (la feature ajoute ~600 lignes maximum).

- [ ] **Step 9.2 : Checklist de vérification manuelle exhaustive**

Sur un dashboard de test (cloner un dashboard PAC hybride existant pour ne pas polluer la prod), avec le dev server lancé ou le build prod déployé :

- [ ] Mode evt — une PAC en défaut comm visible : bande affichée correctement (start = apparition, end = résolution).
- [ ] Mode evt — deux PAC distinctes (50 + 51) avec marqueurs configurés : deux bandes de couleurs différentes (auto = couleur de chaque courbe PAC).
- [ ] Mode evt — défaut en cours (jamais résolu) : bande s'étend jusqu'à `now`, mise à jour visible quand un nouveau point arrive.
- [ ] Mode evt — fenêtre qui commence pendant un défaut : lookback effectue son appel (vérif Network), bande complète après réponse.
- [ ] Mode gap — `gapReferenceKey` configurée avec `gapThresholdSec=600` : un trou de >10 min dans la clé de référence génère une bande, un cycle normal (1/min) n'en génère aucune.
- [ ] Mode gap — la fenêtre contient zéro point pour la clé de référence : toute la fenêtre couverte d'une bande "ongoing".
- [ ] Mode gap — `gapThresholdSec=0` : aucune bande gap même si la clé de référence a des trous.
- [ ] Mode evt + gap activés simultanément avec chevauchement : fusion correcte (une seule bande, pas de superposition).
- [ ] Aucun défaut ni gap sur la fenêtre : rien affiché, aucune erreur console.
- [ ] Pattern `striped` : hachures visibles à la place du remplissage uni.
- [ ] Couleur explicite (`#FF8800` par ex.) : appliquée directement, ignore le mode auto.
- [ ] Tooltip au hover sur la bande : affiche le `label` configuré.
- [ ] Pas de chevauchement parasite avec les `thresholds` existants (les bandes sont en `z: 0`, sous les lignes de seuil).
- [ ] Suppression d'un marqueur depuis les settings → la bande disparaît au re-render.

- [ ] **Step 9.3 : Mettre à jour le statut de la spec**

Éditer `docs/superpowers/specs/2026-06-02-comm-fault-markers-design.md`, changer la ligne :

```
**Statut** : Design approuvé sections 1-3, fichiers touchés en discussion
```

en :

```
**Statut** : Implémenté (plan d'impl `2026-06-02-comm-fault-markers-impl.md`)
```

- [ ] **Step 9.4 : Commit final**

```bash
git add docs/superpowers/specs/2026-06-02-comm-fault-markers-design.md
git commit -m "docs(specs): mark 2026-06-02-comm-fault-markers-design as implemented"
```

- [ ] **Step 9.5 : Reporter les écarts éventuels au user**

Si pendant l'implémentation des écarts ont été nécessaires (ex : signature d'API différente de celle anticipée au Step 8.3, module Angular trouvé à un autre endroit, schéma de FormControl ajusté), les lister explicitement dans le message de fin pour que le user puisse :
- décider d'amender la spec a posteriori
- ajouter une note dans la mémoire projet si la convention découverte est réutilisable

---

## Hors scope (rappel)

- Script Python `patch-time-series-add-evt-markers.py` pour pousser la configuration `eventMarkers` sur des widgets time-series déjà déployés en base — à faire dans un suivi distinct si le user le demande (modèle : `scripts/tb/widgets/patch-events-history-resolution-col.py`).
- Autocomplétion des libellés `FAULT_LABELS` dans le composant settings panel (v2).
- Notification temps-réel "PAC offline depuis X min" (concept différent, hors scope).
- Tests E2E (Cypress/Playwright) — pas en place dans le repo, vérification manuelle au Step 9.2 suffit pour la v1.




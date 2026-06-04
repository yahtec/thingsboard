///
/// Copyright © 2016-2026 The Thingsboard Authors
///
/// Licensed under the Apache License, Version 2.0 (the "License");
/// you may not use this file except in compliance with the License.
/// You may obtain a copy of the License at
///
///     http://www.apache.org/licenses/LICENSE-2.0
///
/// Unless required by applicable law or agreed to in writing, software
/// distributed under the License is distributed on an "AS IS" BASIS,
/// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
/// See the License for the specific language governing permissions and
/// limitations under the License.
///

import {
  reconstructIntervals,
  EventMarkerGroupFilter,
  EventPoint,
  ReconstructedInterval,
  resolveMarkerColor,
  NamedDataKey,
  reconstructGapIntervals,
  mergeIntervals,
  ReferencePoint
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

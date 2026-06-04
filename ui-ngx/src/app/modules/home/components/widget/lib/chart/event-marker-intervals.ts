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

import type { TimeSeriesChartEventMarker } from './time-series-chart.models';

export interface EventPoint {
  ts: number;
  evt_id: number;
  evt_status: number;
  evt_fault: number;
  evt_device: number;
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
      ts: p.evt_id > 0 ? p.evt_id * 1000 : p.ts,
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
    } else if (ev.status === 0) {
      if (openStart !== null) {
        intervals.push({ start: openStart, end: ev.ts, ongoing: false });
        openStart = null;
      } else {
        opts.onOrphanResolution?.(ev.ts);
      }
    }
  }

  if (openStart !== null) {
    intervals.push({ start: openStart, end: opts.now, ongoing: true });
  }

  return intervals;
}

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
  const windowIsOpen = effectiveEnd === opts.now;
  const sorted = [...refs].sort((a, b) => a.ts - b.ts);

  if (sorted.length === 0) {
    return [{
      start: opts.windowStart,
      end: effectiveEnd,
      ongoing: windowIsOpen
    }];
  }

  const boundaries: number[] = [opts.windowStart, ...sorted.map(p => p.ts), effectiveEnd];
  const lastBoundaryIdx = boundaries.length - 2;
  const intervals: ReconstructedInterval[] = [];

  for (let i = 0; i < boundaries.length - 1; i++) {
    const a = boundaries[i];
    const b = boundaries[i + 1];
    if (b - a > thresholdMs) {
      intervals.push({
        start: a,
        end: b,
        ongoing: windowIsOpen && i === lastBoundaryIdx
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

export interface EventMarkerItem {
  config: TimeSeriesChartEventMarker;
  points: EventPoint[];
  lookbackPoints: EventPoint[];
  intervals: ReconstructedInterval[];
  lookbackInFlight: boolean;
}

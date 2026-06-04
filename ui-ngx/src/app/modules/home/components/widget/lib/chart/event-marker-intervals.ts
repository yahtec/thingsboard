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

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

import { Component, DestroyRef, forwardRef, Input, OnInit, ViewEncapsulation } from '@angular/core';
import {
  ControlValueAccessor,
  NG_VALUE_ACCESSOR,
  UntypedFormArray,
  UntypedFormBuilder,
  UntypedFormGroup,
  Validators
} from '@angular/forms';
import {
  TimeSeriesChartEventMarker,
  timeSeriesChartEventMarkerDefaultSettings
} from '@home/components/widget/lib/chart/time-series-chart.models';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

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
  encapsulation: ViewEncapsulation.None,
  standalone: false
})
export class TimeSeriesChartEventMarkersPanelComponent implements OnInit, ControlValueAccessor {

  @Input()
  disabled: boolean;

  eventMarkersFormGroup: UntypedFormGroup;

  private propagateChange = (_val: any) => {};

  constructor(private fb: UntypedFormBuilder,
              private destroyRef: DestroyRef) {}

  ngOnInit(): void {
    this.eventMarkersFormGroup = this.fb.group({
      markers: this.fb.array([])
    });
    this.eventMarkersFormGroup.valueChanges.pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(() => {
      const value = this.markersFormArray.controls.map(c => {
        const raw = c.value as TimeSeriesChartEventMarker & { evtFaultCodes: number[] | string };
        const codes: number[] = typeof raw.evtFaultCodes === 'string'
          ? (raw.evtFaultCodes as string).split(',').map((s: string) => parseInt(s.trim(), 10)).filter((n: number) => !isNaN(n))
          : (raw.evtFaultCodes || []);
        return { ...raw, evtFaultCodes: codes } as TimeSeriesChartEventMarker;
      });
      this.propagateChange(value);
    });
  }

  get markersFormArray(): UntypedFormArray {
    return this.eventMarkersFormGroup.get('markers') as UntypedFormArray;
  }

  registerOnChange(fn: any): void {
    this.propagateChange = fn;
  }

  registerOnTouched(_fn: any): void {}

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
    if (isDisabled) {
      this.eventMarkersFormGroup.disable({ emitEvent: false });
    } else {
      this.eventMarkersFormGroup.enable({ emitEvent: false });
    }
  }

  writeValue(value: TimeSeriesChartEventMarker[] | undefined): void {
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
      evtFaultCodes: [Array.isArray(m.evtFaultCodes) ? m.evtFaultCodes.join(',') : m.evtFaultCodes, []],
      evtDeviceId: [m.evtDeviceId, [Validators.required, Validators.min(0)]],
      gapThresholdSec: [m.gapThresholdSec ?? 0, [Validators.required, Validators.min(0)]],
      gapReferenceKey: [m.gapReferenceKey ?? '', []],
      color: [m.color, [Validators.required]],
      opacity: [m.opacity, [Validators.required, Validators.min(0), Validators.max(1)]],
      pattern: [m.pattern, [Validators.required]]
    });
  }
}

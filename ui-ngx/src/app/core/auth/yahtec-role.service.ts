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

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Store } from '@ngrx/store';
import { Observable, of } from 'rxjs';
import { catchError, map, tap } from 'rxjs/operators';
import { AppState } from '@core/core.state';
import { getCurrentAuthState } from '@core/auth/auth.selectors';
import { Authority } from '@shared/models/authority.enum';

export enum YahtecUiRole { DEV, ADMIN_OPS, CUSTOMER }

const PORTFOLIO_ROLE_KEY = 'portfolioRole';
const ADMIN_OPS_VALUE = 'ADMIN_OPS';
const IS_ADMIN_CACHE_KEY = 'yahtec.user.isAdmin';

@Injectable({ providedIn: 'root' })
export class YahtecRoleService {

    constructor(private store: Store<AppState>, private http: HttpClient) {}

    private authState() { return getCurrentAuthState(this.store); }

    isTenantAdmin(): boolean {
        const a = this.authState()?.authUser?.authority;
        return a === Authority.TENANT_ADMIN || a === Authority.SYS_ADMIN;
    }

    isAdminOps(): boolean {
        if (!this.isTenantAdmin()) { return false; }
        const info = this.authState()?.userDetails?.additionalInfo as Record<string, any> | undefined;
        return !!info && info[PORTFOLIO_ROLE_KEY] === ADMIN_OPS_VALUE;
    }

    isDevTenant(): boolean {
        return this.isTenantAdmin() && !this.isAdminOps();
    }

    resolveRole(): YahtecUiRole {
        if (this.isTenantAdmin()) {
            return this.isAdminOps() ? YahtecUiRole.ADMIN_OPS : YahtecUiRole.DEV;
        }
        return YahtecUiRole.CUSTOMER;
    }

    /** Gate Supervision flotte / Comptes-Paramétrage : tenant admin (dev+ops) OU customer legacy is_admin=true (transition). */
    canAccessAdminFeatures$(): Observable<boolean> {
        if (this.isTenantAdmin()) { return of(true); }
        const authUser = this.authState()?.authUser;
        if (!authUser || authUser.authority !== Authority.CUSTOMER_USER) { return of(false); }
        const cached = sessionStorage.getItem(IS_ADMIN_CACHE_KEY);
        if (cached !== null) { return of(cached === '1'); }
        return this.http.get<Array<{ key: string; value: any }>>(
            `/api/plugins/telemetry/USER/${authUser.userId}/values/attributes/SERVER_SCOPE?keys=is_admin`
        ).pipe(
            map(attrs => (attrs || []).some(a => a.key === 'is_admin' && a.value === true)),
            tap(isAdmin => { try { sessionStorage.setItem(IS_ADMIN_CACHE_KEY, isAdmin ? '1' : '0'); } catch {} }),
            catchError(() => of(false))
        );
    }

    clearCache(): void {
        try { sessionStorage.removeItem(IS_ADMIN_CACHE_KEY); } catch {}
    }
}

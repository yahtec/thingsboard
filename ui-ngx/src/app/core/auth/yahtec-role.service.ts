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
import { catchError, map, retry, tap } from 'rxjs/operators';
import { AppState } from '@core/core.state';
import { getCurrentAuthState } from '@core/auth/auth.selectors';
import { Authority } from '@shared/models/authority.enum';

export enum YahtecUiRole { DEV, ADMIN_OPS, CUSTOMER }

const PORTFOLIO_ROLE_KEY = 'portfolioRole';
const ADMIN_OPS_VALUE = 'ADMIN_OPS';
// Yahtec (I21) : préfixe de clé sessionStorage — la clé effective est scoppée
// par userId (voir cacheKeyFor/cacheKey ci-dessous). Sans ce scoping, une
// session PARTY qui suit (même onglet) une session admin expirée hérite du
// statut admin de l'utilisateur précédent : clearCache() n'était appelé QUE
// dans logout(), jamais sur expiration de session (refresh-token en échec,
// validateJwtToken sans refresh) ni sur login()/loginAsUser().
const IS_ADMIN_CACHE_KEY_PREFIX = 'yahtec.user.isAdmin';

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
        const role = info?.[PORTFOLIO_ROLE_KEY];
        // M-comparaisons : comparaison insensible à la casse (ex. 'admin_ops' posé
        // par un script) — reste null-safe, donc une valeur absente/inattendue
        // échoue toujours vers false (chrome DEV, moindre que ADMIN_OPS).
        return role != null && String(role).toUpperCase() === ADMIN_OPS_VALUE;
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

    private cacheKeyFor(userId: string | undefined): string | undefined {
        return userId ? `${IS_ADMIN_CACHE_KEY_PREFIX}.${userId}` : undefined;
    }

    private cacheKey(): string | undefined {
        return this.cacheKeyFor(this.authState()?.authUser?.userId);
    }

    /** Gate Supervision flotte / Comptes-Paramétrage : tenant admin (dev+ops) OU customer legacy is_admin=true (transition). */
    canAccessAdminFeatures$(): Observable<boolean> {
        if (this.isTenantAdmin()) { return of(true); }
        const authUser = this.authState()?.authUser;
        if (!authUser || authUser.authority !== Authority.CUSTOMER_USER) { return of(false); }
        const key = this.cacheKeyFor(authUser.userId);
        if (key) {
            const cached = sessionStorage.getItem(key);
            if (cached !== null) { return of(cached === '1'); }
        }
        return this.http.get<Array<{ key: string; value: any }>>(
            `/api/plugins/telemetry/USER/${authUser.userId}/values/attributes/SERVER_SCOPE?keys=is_admin`
        ).pipe(
            // I22 : un aléa réseau transitoire ne doit pas retirer les boutons admin
            // pour toute la session SPA — on retente une fois avant d'abandonner.
            retry(1),
            // M-comparaisons : is_admin peut être stocké en string ("true") selon la
            // voie d'écriture (script legacy) — normaliser sans élargir le true-y.
            map(attrs => (attrs || []).some(a => a.key === 'is_admin' && (a.value === true || a.value === 'true'))),
            tap(isAdmin => {
                // Ne mémoriser QUE les réponses HTTP effectivement reçues (succès,
                // même après retry). catchError ci-dessous gère l'échec définitif et
                // ne passe jamais par ce tap : un échec transitoire n'est donc jamais
                // caché comme "false" figé pour le reste de la session (I22).
                if (!key) { return; }
                try { sessionStorage.setItem(key, isAdmin ? '1' : '0'); } catch {}
            }),
            catchError(() => of(false))
        );
    }

    /**
     * Invalide le cache is_admin de l'utilisateur courant puis relance
     * l'évaluation. Permet à l'appelant (Task 14 : re-check sur NavigationEnd)
     * de ne pas faire confiance à un cache potentiellement périmé après un
     * échec HTTP transitoire ou un changement d'attribut serveur en session.
     * Pas d'effet observable pour TENANT_ADMIN/SYS_ADMIN (jamais caché).
     */
    recheck(): Observable<boolean> {
        this.clearCache();
        return this.canAccessAdminFeatures$();
    }

    clearCache(): void {
        const key = this.cacheKey();
        if (!key) { return; }
        try { sessionStorage.removeItem(key); } catch {}
    }
}

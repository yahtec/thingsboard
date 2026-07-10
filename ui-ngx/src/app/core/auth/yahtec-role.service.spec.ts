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

import { TestBed } from '@angular/core/testing';
import { provideMockStore, MockStore } from '@ngrx/store/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { YahtecRoleService, YahtecUiRole } from './yahtec-role.service';
import { Authority } from '@shared/models/authority.enum';

describe('YahtecRoleService', () => {
    let service: YahtecRoleService;
    let store: MockStore;

    function setAuth(authority: Authority, portfolioRole?: string, userId = 'u1') {
        store.setState({ auth: {
            isAuthenticated: true, isUserLoaded: true,
            authUser: { authority, userId, customerId: 'c1' },
            userDetails: { additionalInfo: portfolioRole ? { portfolioRole } : {} }
        }});
    }

    function isAdminUrl(url: string): boolean {
        return url.includes('/values/attributes/SERVER_SCOPE') && url.includes('is_admin');
    }

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [HttpClientTestingModule],
            providers: [YahtecRoleService, provideMockStore()]
        });
        store = TestBed.inject(MockStore);
        service = TestBed.inject(YahtecRoleService);
    });

    afterEach(() => {
        // Nettoie toutes les clés scoppées par userId utilisées par les tests
        // (yahtec.user.isAdmin.<userId>), pas seulement l'ancienne clé unique.
        try {
            Object.keys(sessionStorage)
                .filter(k => k.startsWith('yahtec.user.isAdmin'))
                .forEach(k => sessionStorage.removeItem(k));
        } catch { /* noop */ }
    });

    it('TENANT_ADMIN sans role = DEV', () => {
        setAuth(Authority.TENANT_ADMIN);
        expect(service.resolveRole()).toBe(YahtecUiRole.DEV);
        expect(service.isDevTenant()).toBeTrue();
        expect(service.isAdminOps()).toBeFalse();
    });

    it('TENANT_ADMIN + portfolioRole ADMIN_OPS = ADMIN_OPS', () => {
        setAuth(Authority.TENANT_ADMIN, 'ADMIN_OPS');
        expect(service.resolveRole()).toBe(YahtecUiRole.ADMIN_OPS);
        expect(service.isAdminOps()).toBeTrue();
        expect(service.isDevTenant()).toBeFalse();
        expect(service.isTenantAdmin()).toBeTrue();
    });

    it('CUSTOMER_USER = CUSTOMER (peu importe STAFF/PARTY)', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY');
        expect(service.resolveRole()).toBe(YahtecUiRole.CUSTOMER);
        setAuth(Authority.CUSTOMER_USER, 'STAFF');
        expect(service.resolveRole()).toBe(YahtecUiRole.CUSTOMER);
        expect(service.isTenantAdmin()).toBeFalse();
    });

    it('canAccessAdminFeatures$ = true pour TENANT_ADMIN sans HTTP', (done) => {
        setAuth(Authority.TENANT_ADMIN, 'ADMIN_OPS');
        service.canAccessAdminFeatures$().subscribe(v => { expect(v).toBeTrue(); done(); });
    });

    it('canAccessAdminFeatures$ pour CUSTOMER_USER = fetch legacy is_admin', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY');
        const http = TestBed.inject(HttpTestingController);
        let result: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result = v);
        const req = http.expectOne(r => isAdminUrl(r.url));
        req.flush([{ key: 'is_admin', value: true }]);
        expect(result).toBeTrue();
        http.verify();
    });

    it('clearCache vide le cache sessionStorage scoppé par userId', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'u60');
        try { sessionStorage.setItem('yahtec.user.isAdmin.u60', '1'); } catch { /* noop */ }
        service.clearCache();
        expect(sessionStorage.getItem('yahtec.user.isAdmin.u60')).toBeNull();
    });

    // --- I21 : cache is_admin scoppé par userId ---------------------------

    it('I21 : cache-hit — un second appel du même utilisateur ne refait pas de requête HTTP', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'u20');
        const http = TestBed.inject(HttpTestingController);

        let result1: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result1 = v);
        http.expectOne(r => isAdminUrl(r.url)).flush([{ key: 'is_admin', value: true }]);
        expect(result1).toBeTrue();

        let result2: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result2 = v);
        expect(result2).toBeTrue();
        http.verify(); // aucune requête supplémentaire : la seconde lecture vient du cache
    });

    it('I21 : un second utilisateur (même onglet) ne récupère PAS le cache du premier — le bug reproduit', () => {
        // Reproduit le scénario du finding : session admin/PARTY A expirée puis
        // login PARTY B dans le même onglet. Avant le fix, la clé sessionStorage
        // non scoppée était partagée par tous les utilisateurs : B aurait hérité
        // du statut is_admin de A. La clé scoppée par userId élimine ce risque
        // structurellement, sans dépendre d'un appel explicite à clearCache().
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'userA');
        const http = TestBed.inject(HttpTestingController);

        let resultA: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => resultA = v);
        http.expectOne(r => isAdminUrl(r.url)).flush([{ key: 'is_admin', value: true }]);
        expect(resultA).toBeTrue();
        expect(sessionStorage.getItem('yahtec.user.isAdmin.userA')).toBe('1');

        // Changement d'utilisateur dans le même onglet, SANS appel explicite à
        // clearCache() (simule l'un des chemins de staleness du finding : expiration
        // de session puis login d'un autre utilisateur).
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'userB');

        let resultB: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => resultB = v);
        // Doit re-fetch : aucune entrée sous la clé de userB.
        const req = http.expectOne(r => isAdminUrl(r.url));
        req.flush([{ key: 'is_admin', value: false }]);
        expect(resultB).toBeFalse();
        http.verify();
    });

    // --- I22 : retry(1) + pas de mise en cache d'un échec ------------------

    it('I22 : retry(1) — premier échec HTTP puis succès au second essai', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'u10');
        const http = TestBed.inject(HttpTestingController);

        let result: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result = v);

        http.expectOne(r => isAdminUrl(r.url)).error(new ProgressEvent('network error'));
        const retryReq = http.expectOne(r => isAdminUrl(r.url));
        retryReq.flush([{ key: 'is_admin', value: true }]);

        expect(result).toBeTrue();
        expect(sessionStorage.getItem('yahtec.user.isAdmin.u10')).toBe('1');
        http.verify();
    });

    it('I22 : échec persistant (après retry) => false, jamais mis en cache', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'u11');
        const http = TestBed.inject(HttpTestingController);

        let result1: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result1 = v);
        http.expectOne(r => isAdminUrl(r.url)).error(new ProgressEvent('network error'));
        http.expectOne(r => isAdminUrl(r.url)).error(new ProgressEvent('network error'));

        expect(result1).toBeFalse();
        expect(sessionStorage.getItem('yahtec.user.isAdmin.u11')).toBeNull();

        // Un appel suivant doit re-fetch : l'échec transitoire n'a pas figé
        // "false" pour le reste de la session SPA (c'était le bug #22).
        let result2: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result2 = v);
        http.expectOne(r => isAdminUrl(r.url)).flush([{ key: 'is_admin', value: true }]);
        expect(result2).toBeTrue();
        http.verify();
    });

    it('I22 : recheck() invalide le cache et relance le fetch HTTP', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'u30');
        const http = TestBed.inject(HttpTestingController);

        service.canAccessAdminFeatures$().subscribe();
        http.expectOne(r => isAdminUrl(r.url)).flush([{ key: 'is_admin', value: true }]);
        expect(sessionStorage.getItem('yahtec.user.isAdmin.u30')).toBe('1');

        let result: boolean | undefined;
        service.recheck().subscribe(v => result = v);
        http.expectOne(r => isAdminUrl(r.url)).flush([{ key: 'is_admin', value: false }]);
        expect(result).toBeFalse();
        expect(sessionStorage.getItem('yahtec.user.isAdmin.u30')).toBe('0');
        http.verify();
    });

    // --- M-comparaisons : normalisation ------------------------------------

    it('M-comparaisons : portfolioRole insensible à la casse ("admin_ops")', () => {
        setAuth(Authority.TENANT_ADMIN, 'admin_ops');
        expect(service.isAdminOps()).toBeTrue();
        expect(service.resolveRole()).toBe(YahtecUiRole.ADMIN_OPS);
    });

    it('M-comparaisons : is_admin = "true" (string) traité comme true', () => {
        setAuth(Authority.CUSTOMER_USER, 'PARTY', 'u40');
        const http = TestBed.inject(HttpTestingController);
        let result: boolean | undefined;
        service.canAccessAdminFeatures$().subscribe(v => result = v);
        http.expectOne(r => isAdminUrl(r.url)).flush([{ key: 'is_admin', value: 'true' }]);
        expect(result).toBeTrue();
        http.verify();
    });

    // --- I24 (pinning) ------------------------------------------------------

    // Modèle prod post-migration : un compte ADMIN_OPS est TOUJOURS créé en
    // TENANT_ADMIN (jamais customerId). migrate_legacy_to_rbac.py hard-fail
    // désormais sur la création d'un hybride CUSTOMER_USER + portfolioRole=
    // ADMIN_OPS (cf. revue de bugs RBAC, finding #13/#24 : un tel hybride était
    // scopé au party-customer côté TB tout en étant considéré "unrestricted"
    // côté RBAC — incohérence dangereuse). Ce test verrouille le rendu attendu
    // si un tel hybride existait malgré tout (bug résiduel, données corrompues,
    // etc.) : isAdminOps() exige isTenantAdmin() en amont, donc AUCUNE feature
    // admin n'est jamais accordée à un CUSTOMER_USER, quel que soit portfolioRole.
    it('I24 (pin) : CUSTOMER_USER avec portfolioRole=ADMIN_OPS ne doit PAS obtenir isAdminOps()', () => {
        setAuth(Authority.CUSTOMER_USER, 'ADMIN_OPS', 'u50');
        expect(service.isAdminOps()).toBeFalse();
        expect(service.resolveRole()).toBe(YahtecUiRole.CUSTOMER);
        expect(service.isDevTenant()).toBeFalse();
    });
});

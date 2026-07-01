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

    function setAuth(authority: Authority, portfolioRole?: string) {
        store.setState({ auth: {
            isAuthenticated: true, isUserLoaded: true,
            authUser: { authority, userId: 'u1', customerId: 'c1' },
            userDetails: { additionalInfo: portfolioRole ? { portfolioRole } : {} }
        }});
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
        try { sessionStorage.removeItem('yahtec.user.isAdmin'); } catch {}
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
        const req = http.expectOne(r => r.url.includes('/values/attributes/SERVER_SCOPE') && r.url.includes('is_admin'));
        req.flush([{ key: 'is_admin', value: true }]);
        expect(result).toBeTrue();
        http.verify();
    });

    it('clearCache vide le cache sessionStorage', () => {
        try { sessionStorage.setItem('yahtec.user.isAdmin', '1'); } catch {}
        service.clearCache();
        expect(sessionStorage.getItem('yahtec.user.isAdmin')).toBeNull();
    });
});

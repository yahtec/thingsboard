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
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { YahtecRoleService } from '@core/auth/yahtec-role.service';
import { Authority } from '@shared/models/authority.enum';

// Fork Yahtec : intention de la garde du crayon « mode édition » des dashboards,
// implementee par DashboardPageComponent.canEditDashboards() qui delegue a
// YahtecRoleService.isDashboardEditor().
//
// ui-ngx n'a pas de lanceur de tests a ce jour : pas de cible `test` dans
// angular.json, ni karma, ni jest, ni jasmine dans les dependances ; le pom.xml
// ne lance que `yarn build:prod`. Ce fichier consigne le comportement attendu
// pour le jour ou un lanceur sera monte. La verification effective se fait par
// compilation, puis en production sous chaque role.
describe('Garde du crayon d edition de dashboard', () => {
    let roleService: YahtecRoleService;
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
        roleService = TestBed.inject(YahtecRoleService);
    });

    it('un TENANT_ADMIN marque DEV peut editer', () => {
        setAuth(Authority.TENANT_ADMIN, 'DEV');
        expect(roleService.isDashboardEditor()).toBeTrue();
    });

    it('le marqueur est insensible a la casse', () => {
        setAuth(Authority.TENANT_ADMIN, 'dev');
        expect(roleService.isDashboardEditor()).toBeTrue();
    });

    it('un ADMIN_OPS cote client ne peut pas editer', () => {
        setAuth(Authority.TENANT_ADMIN, 'ADMIN_OPS');
        expect(roleService.isDashboardEditor()).toBeFalse();
    });

    it('fail-closed : un TENANT_ADMIN sans marqueur ne peut pas editer', () => {
        // Cas de svc-tbnotify@ (compte de service), des comptes livres par
        // ThingsBoard, et de tout compte cree a la main dans l'IHM. C'est la
        // raison d'etre de isDashboardEditor() : isDevTenant(), qui se definit
        // par l'ABSENCE de ADMIN_OPS, aurait autorise ces comptes.
        setAuth(Authority.TENANT_ADMIN);
        expect(roleService.isDashboardEditor()).toBeFalse();
        expect(roleService.isDevTenant()).toBeTrue();
    });

    it('un utilisateur client ne peut pas editer', () => {
        setAuth(Authority.CUSTOMER_USER);
        expect(roleService.isDashboardEditor()).toBeFalse();
    });

    it('le marqueur seul ne suffit pas : l autorite est verifiee aussi', () => {
        setAuth(Authority.CUSTOMER_USER, 'DEV');
        expect(roleService.isDashboardEditor()).toBeFalse();
    });

    it('les trois bandeaux ne bougent pas : DEV n est pas ADMIN_OPS', () => {
        setAuth(Authority.TENANT_ADMIN, 'DEV');
        expect(roleService.isAdminOps()).toBeFalse();
        expect(roleService.isDevTenant()).toBeTrue();
    });
});

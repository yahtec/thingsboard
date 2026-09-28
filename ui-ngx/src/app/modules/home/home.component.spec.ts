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
import { ReactiveFormsModule } from '@angular/forms';
import { provideMockStore, MockStore } from '@ngrx/store/testing';
import { of } from 'rxjs';
import { Router } from '@angular/router';
import { BreakpointObserver } from '@angular/cdk/layout';
import { HomeComponent } from './home.component';
import { Authority } from '@shared/models/authority.enum';
import { WINDOW } from '@core/services/window.service';
import { ActiveComponentService } from '@core/services/active-component.service';
import { AuthService } from '@core/auth/auth.service';
import { YahtecRoleService } from '@core/auth/yahtec-role.service';
import { YAHTEC_MES_INSTALLATIONS_V1_ID } from '@core/auth/yahtec-dashboards';

// I20 : réactivité du chrome au changement d'utilisateur (impersonation « Login
// as user »). HomeComponent est instancié comme fournisseur DI (sans rendu de
// template : les @ViewChild ne sont pas câblés, mais la logique de ngOnInit et
// des souscriptions store est pleinement testable).
describe('HomeComponent — chrome réactif (I20)', () => {

    let component: HomeComponent;
    let store: MockStore;

    const recheckSpy = jasmine.createSpy('recheck');
    const yahtecRoleStub: any = { recheck: recheckSpy };

    const windowStub: any = {
        location: { pathname: '/dashboards/x', href: 'http://localhost/dashboards/x', assign: () => {} },
        addEventListener: () => {},
        removeEventListener: () => {},
        history: { back: () => {} }
    };
    const routerStub: any = { events: of(), url: '/dashboards/x' };
    const bpStub: any = { isMatched: () => true, observe: () => of({ matches: true, breakpoints: {} }) };

    function authWrap(authority: Authority, userId: string, portfolioRole?: string) {
        return {
            auth: {
                isAuthenticated: true,
                isUserLoaded: true,
                authUser: { authority, userId, customerId: 'c1' },
                userDetails: { additionalInfo: portfolioRole ? { portfolioRole } : {} }
            }
        };
    }

    beforeEach(() => {
        recheckSpy.calls.reset();
        // recheck #1 => true (accès Comptes), #2 => false, #3 (garde) => false.
        recheckSpy.and.returnValues(of(true), of(false), of(false));
        TestBed.configureTestingModule({
            imports: [ReactiveFormsModule],
            providers: [
                HomeComponent,
                provideMockStore({ initialState: authWrap(Authority.TENANT_ADMIN, 'devUser') }),
                { provide: WINDOW, useValue: windowStub },
                { provide: Router, useValue: routerStub },
                { provide: BreakpointObserver, useValue: bpStub },
                { provide: ActiveComponentService, useValue: {} },
                { provide: AuthService, useValue: {} },
                { provide: YahtecRoleService, useValue: yahtecRoleStub }
            ]
        });
        store = TestBed.inject(MockStore);
        component = TestBed.inject(HomeComponent);
    });

    it('dérive le chrome natif TB pour un TENANT_ADMIN « dev » à l\'initialisation', () => {
        component.ngOnInit();
        expect(component.isAdmin).toBeTrue();
        expect(component.forceFullscreen).toBeFalse();
        expect(component.yahtecCanAccessComptes).toBeTrue(); // recheck #1 => of(true)
        expect(recheckSpy).toHaveBeenCalledTimes(1);
    });

    it('bascule en chrome customer après « Login as user » vers un PARTY (sans F5)', () => {
        component.ngOnInit();
        expect(component.isAdmin).toBeTrue();

        // Impersonation : le store est remplacé, le shell HomeComponent réutilisé.
        store.setState(authWrap(Authority.CUSTOMER_USER, 'partyUser', 'PARTY'));

        expect(component.isAdmin).toBeFalse();
        expect(component.forceFullscreen).toBeTrue();
        expect(component.yahtecCanAccessComptes).toBeFalse(); // recheck #2 => of(false)
        expect(recheckSpy).toHaveBeenCalledTimes(2);
    });

    it('un TENANT_ADMIN ADMIN_OPS reçoit le chrome customer (isAdmin=false)', () => {
        component.ngOnInit();
        store.setState(authWrap(Authority.TENANT_ADMIN, 'opsUser', 'ADMIN_OPS'));
        expect(component.isAdmin).toBeFalse();
        expect(component.forceFullscreen).toBeTrue();
    });

    it('ne relance pas recheck() sur une émission sans changement d\'utilisateur', () => {
        component.ngOnInit();
        expect(recheckSpy).toHaveBeenCalledTimes(1);
        // Même utilisateur/rôle ré-émis (ex. changement de userSettings) :
        // distinctUntilChanged bloque, aucun re-fetch is_admin.
        store.setState(authWrap(Authority.TENANT_ADMIN, 'devUser'));
        expect(recheckSpy).toHaveBeenCalledTimes(1);
    });
});

// Bouton « Tableau de bord » : il vise le dashboard d'atterrissage du COMPTE
// (additionalInfo.defaultDashboardId). En dur sur la V1, il donnait un 403 aux
// portefeuilles dont la V1 avait été décrochée (2026-09-11).
describe('HomeComponent — bouton « Tableau de bord »', () => {

    let component: HomeComponent;
    let store: MockStore;
    const assignSpy = jasmine.createSpy('assign');
    const location: any = { pathname: '/', href: 'http://localhost/', assign: assignSpy };
    const windowStub: any = {
        location,
        addEventListener: () => {},
        removeEventListener: () => {},
        history: { back: () => {} }
    };
    const bpStub: any = { isMatched: () => true, observe: () => of({ matches: true, breakpoints: {} }) };

    const LANDING = 'dashboard-atterrissage-du-compte';

    function customerState(defaultDashboardId: string | undefined = LANDING) {
        const additionalInfo: Record<string, any> = { portfolioRole: 'PARTY' };
        if (defaultDashboardId) { additionalInfo.defaultDashboardId = defaultDashboardId; }
        return {
            auth: {
                isAuthenticated: true,
                isUserLoaded: true,
                authUser: { authority: Authority.CUSTOMER_USER, userId: 'partyUser', customerId: 'c1' },
                userDetails: { additionalInfo }
            }
        };
    }

    function openAt(path: string) {
        location.pathname = path;
        location.href = 'http://localhost' + path;
        component.ngOnInit();
    }

    beforeEach(() => {
        assignSpy.calls.reset();
        TestBed.configureTestingModule({
            imports: [ReactiveFormsModule],
            providers: [
                HomeComponent,
                provideMockStore({ initialState: customerState() }),
                { provide: WINDOW, useValue: windowStub },
                { provide: Router, useValue: { events: of(), url: '/' } },
                { provide: BreakpointObserver, useValue: bpStub },
                { provide: ActiveComponentService, useValue: {} },
                { provide: AuthService, useValue: {} },
                { provide: YahtecRoleService, useValue: { recheck: () => of(false) } }
            ]
        });
        store = TestBed.inject(MockStore);
        component = TestBed.inject(HomeComponent);
    });

    it("mène au dashboard d'atterrissage du compte, pas à la V1", () => {
        openAt('/profile');
        expect(component.yahtecShowGoToDashboard).toBeTrue();
        component.yahtecGoToDashboard();
        expect(assignSpy).toHaveBeenCalledWith('/dashboards/' + LANDING);
    });

    it("sans dashboard d'atterrissage, il mène à l'accueil ThingsBoard", () => {
        store.setState(customerState(undefined));
        openAt('/profile');
        component.yahtecGoToDashboard();
        expect(assignSpy).toHaveBeenCalledWith('/home');
    });

    it("est masqué sur le dashboard d'atterrissage, qui porte sa propre navigation", () => {
        openAt('/dashboards/' + LANDING);
        expect(component.yahtecOnLanding).toBeTrue();
        expect(component.yahtecShowGoToDashboard).toBeFalse();
        // La barre yahtec ne connaît que les états V1 : elle reste éteinte sur la v2.
        expect(component.yahtecOnDashboard).toBeFalse();
        expect(component.yahtecShowAccueil).toBeFalse();
        expect(component.yahtecShowProfil).toBeFalse();
    });

    it('est masqué sur la V1, dont la barre yahtec a son bouton Accueil', () => {
        openAt('/dashboards/' + YAHTEC_MES_INSTALLATIONS_V1_ID);
        expect(component.yahtecOnDashboard).toBeTrue();
        expect(component.yahtecShowGoToDashboard).toBeFalse();
    });

    it('n\'est jamais montré à un admin « dev » (chrome TB natif)', () => {
        store.setState({
            auth: {
                isAuthenticated: true,
                isUserLoaded: true,
                authUser: { authority: Authority.TENANT_ADMIN, userId: 'devUser', customerId: null },
                userDetails: { additionalInfo: { portfolioRole: 'DEV' } }
            }
        });
        openAt('/profile');
        expect(component.isAdmin).toBeTrue();
        expect(component.yahtecShowGoToDashboard).toBeFalse();
    });
});

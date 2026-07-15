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
import { provideMockStore } from '@ngrx/store/testing';
import { of } from 'rxjs';
import { Router } from '@angular/router';
import { DatePipe } from '@angular/common';
import { MatDialog } from '@angular/material/dialog';
import { TranslateService } from '@ngx-translate/core';
import { Authority } from '@shared/models/authority.enum';
import { YahtecRoleService } from '@core/auth/yahtec-role.service';
import { DashboardService } from '@app/core/http/dashboard.service';
import { CustomerService } from '@core/http/customer.service';
import { EdgeService } from '@core/http/edge.service';
import { DialogService } from '@core/services/dialog.service';
import { HomeDialogsService } from '@home/dialogs/home-dialogs.service';
import { ImportExportService } from '@shared/import-export/import-export.service';
import { DashboardsTableConfigResolver } from './dashboards-table-config.resolver';

// M-totalElements : yahtecFilterAdminDashboards() ne doit retrancher de
// totalElements QUE les lignes réellement retirées de la page courante, et non
// écraser le total serveur multi-pages (ce qui cassait la pagination de la
// table de dashboards pour les CUSTOMER_USER sans is_admin).
describe('DashboardsTableConfigResolver.yahtecFilterAdminDashboards (M-totalElements)', () => {

    const RESTRICTED = '4aa4ccd0-422a-11f1-bbfe-e1395562cba0';
    let resolver: any; // accès à la méthode privée yahtecFilterAdminDashboards
    let canAccessAdminSpy: jasmine.Spy;

    beforeEach(() => {
        canAccessAdminSpy = jasmine.createSpy('canAccessAdminFeatures$').and.returnValue(of(false));
        const yahtecRoleStub: any = { canAccessAdminFeatures$: canAccessAdminSpy };
        TestBed.configureTestingModule({
            providers: [
                DashboardsTableConfigResolver,
                provideMockStore({
                    initialState: { auth: { authUser: { authority: Authority.CUSTOMER_USER, userId: 'u1', customerId: 'c1' } } }
                }),
                { provide: YahtecRoleService, useValue: yahtecRoleStub },
                // Dépendances non sollicitées par yahtecFilterAdminDashboards : stubs vides.
                { provide: DashboardService, useValue: {} },
                { provide: CustomerService, useValue: {} },
                { provide: EdgeService, useValue: {} },
                { provide: DialogService, useValue: {} },
                { provide: HomeDialogsService, useValue: {} },
                { provide: ImportExportService, useValue: {} },
                { provide: TranslateService, useValue: { instant: (k: string) => k } },
                { provide: DatePipe, useValue: {} },
                { provide: Router, useValue: {} },
                { provide: MatDialog, useValue: {} }
            ]
        });
        resolver = TestBed.inject(DashboardsTableConfigResolver);
    });

    it('retranche uniquement la ligne restreinte retirée, préserve total + hasNext', (done) => {
        const page = {
            data: [{ id: { id: 'a' } }, { id: { id: RESTRICTED } }, { id: { id: 'b' } }],
            totalPages: 5,
            totalElements: 42, // total serveur multi-pages
            hasNext: true
        };
        resolver.yahtecFilterAdminDashboards(page).subscribe((result: any) => {
            expect(result.data.map((d: any) => d.id.id)).toEqual(['a', 'b']); // restreint retiré
            expect(result.totalElements).toBe(41); // 42 - 1 retiré (PAS 2 = filtered.length)
            expect(result.hasNext).toBeTrue(); // pagination serveur préservée
            expect(result.totalPages).toBe(5);
            done();
        });
    });

    it('renvoie la page inchangée si aucun dashboard restreint n\'est présent', (done) => {
        const page = { data: [{ id: { id: 'a' } }], totalPages: 1, totalElements: 7, hasNext: false };
        resolver.yahtecFilterAdminDashboards(page).subscribe((result: any) => {
            expect(result).toBe(page); // court-circuit : même référence
            expect(result.totalElements).toBe(7);
            done();
        });
    });

    it('ne filtre rien pour un admin legacy (is_admin=true) même si un restreint est présent', (done) => {
        canAccessAdminSpy.and.returnValue(of(true));
        const page = {
            data: [{ id: { id: 'a' } }, { id: { id: RESTRICTED } }],
            totalPages: 3,
            totalElements: 20,
            hasNext: true
        };
        resolver.yahtecFilterAdminDashboards(page).subscribe((result: any) => {
            expect(result).toBe(page);
            expect(result.data.length).toBe(2);
            expect(result.totalElements).toBe(20);
            done();
        });
    });
});

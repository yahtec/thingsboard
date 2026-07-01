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

import { Injectable, NgModule } from '@angular/core';
import { ActivatedRouteSnapshot, Router, RouterModule, Routes } from '@angular/router';

import { EntitiesTableComponent } from '../../components/entity/entities-table.component';
import { Authority } from '@shared/models/authority.enum';
import { DashboardsTableConfigResolver } from './dashboards-table-config.resolver';
import { DashboardPageComponent } from '@home/components/dashboard-page/dashboard-page.component';
import { BreadCrumbConfig, BreadCrumbLabelFunction } from '@shared/components/breadcrumb';
import { mergeMap, Observable, of, throwError } from 'rxjs';
import { Dashboard } from '@app/shared/models/dashboard.models';
import { DashboardService } from '@core/http/dashboard.service';
import { DashboardUtilsService } from '@core/services/dashboard-utils.service';
import { catchError, map } from 'rxjs/operators';

import { UserSettingsService } from '@core/http/user-settings.service';
import { UserDashboardAction } from '@shared/models/user-settings.models';
import { Store } from '@ngrx/store';
import { AppState } from '@core/core.state';
import { getCurrentAuthUser } from '@core/auth/auth.selectors';
import { ConfirmOnExitGuard } from '@core/guards/confirm-on-exit.guard';
import { MenuId } from '@core/services/menu.models';
import { YahtecRoleService } from '@core/auth/yahtec-role.service';

// Yahtec : dashboards reserves aux admins (TENANT_ADMIN OR CUSTOMER_USER avec is_admin=true)
const YAHTEC_SUPERVISION_DASHBOARD_ID = '4aa4ccd0-422a-11f1-bbfe-e1395562cba0';
const YAHTEC_MES_INSTALLATIONS_ID     = '0964da30-3e56-11f1-bbfe-e1395562cba0';
const YAHTEC_ADMIN_RESTRICTED_DASHBOARDS = new Set<string>([YAHTEC_SUPERVISION_DASHBOARD_ID]);

@Injectable()
export class DashboardResolver  {

  constructor(private store: Store<AppState>,
              private dashboardService: DashboardService,
              private userSettingService: UserSettingsService,
              private dashboardUtils: DashboardUtilsService,
              private yahtecRole: YahtecRoleService,
              private router: Router) {
  }

  resolve(route: ActivatedRouteSnapshot): Observable<Dashboard> {
    const dashboardId = route.params.dashboardId;
    // Yahtec : bloquer l'acces aux dashboards admin-only (Supervision flotte) pour
    // les CUSTOMER_USER sans attribute is_admin=true. TENANT_ADMIN/SYS_ADMIN ont
    // toujours acces.
    if (YAHTEC_ADMIN_RESTRICTED_DASHBOARDS.has(dashboardId)) {
      const authUser = getCurrentAuthUser(this.store);
      if (authUser && authUser.authority === Authority.CUSTOMER_USER) {
        return this.yahtecRole.canAccessAdminFeatures$().pipe(
          mergeMap(isAdmin => {
            if (!isAdmin) {
              this.router.navigate(['dashboards', YAHTEC_MES_INSTALLATIONS_ID]);
              return throwError(() => new Error('Yahtec admin-only dashboard'));
            }
            return this.loadDashboard(dashboardId);
          })
        );
      }
    }
    return this.loadDashboard(dashboardId);
  }

  private loadDashboard(dashboardId: string): Observable<Dashboard> {
    return this.dashboardService.getDashboard(dashboardId).pipe(
      mergeMap((dashboard) =>
        (getCurrentAuthUser(this.store).isPublic ? of(null) :
          this.userSettingService.reportUserDashboardAction(dashboardId, UserDashboardAction.VISIT,
            {ignoreLoading: true, ignoreErrors: true})).pipe(
          catchError(() => of(dashboard)),
          map(() => dashboard)
        )),
      map((dashboard) => this.dashboardUtils.validateAndUpdateDashboard(dashboard))
    );
  }
}

export const dashboardBreadcumbLabelFunction: BreadCrumbLabelFunction<DashboardPageComponent>
  = ((route, translate, component) => component.dashboard.title);

const routes: Routes = [
  {
    path: 'dashboards',
    data: {
      breadcrumb: {
        menuId: MenuId.dashboards
      }
    },
    children: [
      {
        path: '',
        component: EntitiesTableComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: 'dashboard.dashboards',
          dashboardsType: 'tenant'
        },
        resolve: {
          entitiesTableConfig: DashboardsTableConfigResolver
        }
      },
      {
        path: ':dashboardId',
        component: DashboardPageComponent,
        canDeactivate: [ConfirmOnExitGuard],
        data: {
          breadcrumb: {
            labelFunction: dashboardBreadcumbLabelFunction,
            icon: 'dashboard'
          } as BreadCrumbConfig<DashboardPageComponent>,
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: 'dashboard.dashboard',
          widgetEditMode: false
        },
        resolve: {
          dashboard: DashboardResolver
        }
      }
    ]
  }
];

// @dynamic
@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
  providers: [
    DashboardsTableConfigResolver,
    DashboardResolver
  ]
})
export class DashboardRoutingModule { }

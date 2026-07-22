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

import { AfterViewInit, Component, ElementRef, Inject, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { skip, startWith, Subject } from 'rxjs';
import { select, Store } from '@ngrx/store';
import { debounceTime, distinctUntilChanged, switchMap, takeUntil, tap } from 'rxjs/operators';

import { BreakpointObserver, BreakpointState } from '@angular/cdk/layout';
import { PageComponent } from '@shared/components/page.component';
import { AppState } from '@core/core.state';
import { getCurrentAuthState, selectAuth } from '@core/auth/auth.selectors';
import { MediaBreakpoints } from '@shared/models/constants';
import screenfull from 'screenfull';
import { MatSidenav } from '@angular/material/sidenav';
import { AuthState } from '@core/auth/auth.models';
import { WINDOW } from '@core/services/window.service';
import { instanceOfSearchableComponent, ISearchableComponent } from '@home/models/searchable-component.models';
import { ActiveComponentService } from '@core/services/active-component.service';
import { RouterTabsComponent } from '@home/components/router-tabs.component';
import { FormBuilder } from '@angular/forms';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import { isDefined, isDefinedAndNotNull } from '@core/utils';
import { Authority } from '@shared/models/authority.enum';
import { filter } from 'rxjs/operators';
import { AuthService } from '@core/auth/auth.service';
import { YahtecRoleService } from '@core/auth/yahtec-role.service';

// Yahtec : dashboard "Mes Installations" custom navigation
const YAHTEC_DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0';
// Yahtec : dashboard "Supervision flotte" (admin only : TENANT_ADMIN ou is_admin=true)
const YAHTEC_SUPERVISION_ID = '4aa4ccd0-422a-11f1-bbfe-e1395562cba0';
type YahtecState = 'menu' | 'default' | 'donnees_HP1' | 'depart_chauffage' | 'ecs'
                 | 'historique' | 'fault_diagnostic' | 'configuration' | 'profil'
                 | 'notifications_admin';

@Component({
    selector: 'tb-home',
    templateUrl: './home.component.html',
    styleUrls: ['./home.component.scss'],
    standalone: false
})
export class HomeComponent extends PageComponent implements AfterViewInit, OnInit, OnDestroy {

  authState: AuthState = getCurrentAuthState(this.store);

  // Yahtec: distinction entre la navbar "native ThingsBoard" (pour les
  // TENANT_ADMIN dev — conserve tout : github badge, fullscreen, menu 3 points,
  // sidebar) et la navbar "custom TSmart" (pour les CUSTOMER_USER ET les
  // TENANT_ADMIN ADMIN_OPS — simplifiée : barre custom, pas de sidebar).
  // Les ADMIN_OPS (portfolioRole=ADMIN_OPS) restent TENANT_ADMIN côté backend
  // (accès unrestricted) mais reçoivent le chrome customer TSmart.
  // I20 : valeur initiale au constructor (rendu de premier affichage identique à
  // l'existant) ; ré-évaluée ensuite à chaque changement d'utilisateur via une
  // souscription live au store (voir ngOnInit + recomputeYahtecChrome).
  isAdmin = this.computeIsAdmin(this.authState);

  // La sidebar latérale est masquée pour les non-admins et les ADMIN_OPS (= mode TSmart custom).
  forceFullscreen = !this.isAdmin;

  // Yahtec : navbar TB native customisee pour le dashboard "Mes Installations"
  yahtecOnDashboard = false;           // true quand l'URL pointe sur Mes Installations
  yahtecOnSupervision = false;         // true quand l'URL pointe sur Supervision flotte
  yahtecStateId: YahtecState = 'menu'; // state actuel dans l'URL ?state=...
  yahtecCanAccessComptes = false;      // TENANT_ADMIN OU CUSTOMER_USER avec is_admin=true

  activeComponent: any;
  searchableComponent: ISearchableComponent;

  sidenavMode: 'over' | 'push' | 'side' = 'side';
  sidenavOpened = true;

  // Yahtec / Terris Energy branding: flame mark + "TSmart" wordmark.
  // Original ThingsBoard logo is kept at assets/logo_title_white.svg for reference;
  // switch the path back if you need to revert without rebuilding the navbar.
  logo = 'assets/yahtec/logo_tsmart_white.svg';

  @ViewChild('sidenav')
  sidenav: MatSidenav;

  @ViewChild('mainContent', { static: true }) mainContent: ElementRef<HTMLElement>;

  @ViewChild('searchInput') searchInputField: ElementRef;

  fullscreenEnabled = screenfull.isEnabled;

  searchEnabled = false;
  showSearch = false;
  textSearch = this.fb.control('', {nonNullable: true});

  hideLoadingBar = false;

  private destroy$ = new Subject<void>();

  constructor(protected store: Store<AppState>,
              @Inject(WINDOW) private window: Window,
              private activeComponentService: ActiveComponentService,
              private fb: FormBuilder,
              private router: Router,
              private authService: AuthService,
              private yahtecRole: YahtecRoleService,
              public breakpointObserver: BreakpointObserver) {
    super(store);
  }

  ngOnInit() {

    const isGtSm = this.breakpointObserver.isMatched(MediaBreakpoints['gt-sm']);
    this.sidenavMode = isGtSm ? 'side' : 'over';
    this.sidenavOpened = isGtSm;

    this.breakpointObserver
      .observe(MediaBreakpoints['gt-sm'])
      .pipe(takeUntil(this.destroy$))
      .subscribe((state: BreakpointState) => {
          if (state.matches) {
            this.sidenavMode = 'side';
            this.sidenavOpened = true;
          } else {
            this.sidenavMode = 'over';
            this.sidenavOpened = false;
          }
        }
      );

    // Yahtec : initialise + observe l'URL pour mettre a jour yahtecOnDashboard + yahtecStateId
    this.updateYahtecNavState();
    this.router.events.pipe(
      filter(e => e instanceof NavigationEnd),
      takeUntil(this.destroy$),
    ).subscribe(() => this.updateYahtecNavState());
    // popstate : Mes Installations change le state via history.pushState + popstate synth
    this.window.addEventListener('popstate', this.yahtecOnPopstate);

    // I20 : le chrome (isAdmin / forceFullscreen / accès Comptes) est dérivé d'une
    // souscription LIVE au store d'auth, et non plus d'un calcul one-shot au
    // constructor/ngOnInit. Après « Login as user », l'impersonation remplace
    // l'utilisateur dans le store mais réutilise le shell HomeComponent (pas de
    // recréation) : sans cette souscription, un PARTY impersoné conservait le
    // chrome natif TB complet + les boutons Comptes/Paramétrage jusqu'à un F5.
    // On re-dérive isAdmin/forceFullscreen (synchrone) puis on relance recheck()
    // (Task 13 : invalide le cache is_admin périmé de l'utilisateur précédent)
    // à chaque changement effectif d'utilisateur. La souscription émet aussi
    // immédiatement à l'abonnement, ce qui remplace l'ancien
    // checkYahtecComptesAccess() une-fois.
    this.store.pipe(
      select(selectAuth),
      filter(state => !!state?.authUser),
      distinctUntilChanged((a, b) => this.yahtecAuthKey(a) === this.yahtecAuthKey(b)),
      tap(state => this.recomputeYahtecChrome(state)),
      switchMap(() => this.yahtecRole.recheck()),
      takeUntil(this.destroy$)
    ).subscribe(canAccess => this.yahtecCanAccessComptes = canAccess);
  }

  private yahtecOnPopstate = () => this.updateYahtecNavState();

  // I20 : logique isAdmin factorisée (source unique partagée par l'initialiseur de
  // champ et la re-dérivation réactive). isAdmin = admin TB « dev » (TENANT_ADMIN/
  // SYS_ADMIN SANS portfolioRole=ADMIN_OPS) → chrome natif TB. Les ADMIN_OPS et
  // CUSTOMER_USER reçoivent le chrome TSmart custom.
  private computeIsAdmin(state: AuthState): boolean {
    return (state?.authUser?.authority === Authority.SYS_ADMIN
        || state?.authUser?.authority === Authority.TENANT_ADMIN)
      && (state?.userDetails?.additionalInfo as Record<string, any>)?.['portfolioRole'] !== 'ADMIN_OPS';
  }

  // I20 : clé de dédup — ne relance la re-dérivation + recheck() que sur un
  // changement effectif d'utilisateur ou de rôle (évite un fetch is_admin à
  // chaque émission du store, ex. changement de userSettings).
  private yahtecAuthKey(state: AuthState): string {
    const u = state?.authUser;
    const role = (state?.userDetails?.additionalInfo as Record<string, any>)?.['portfolioRole'];
    return `${u?.authority}|${u?.userId}|${role}`;
  }

  // I20 : re-dérivation synchrone du chrome à partir d'un état d'auth donné.
  private recomputeYahtecChrome(state: AuthState) {
    this.authState = state;
    this.isAdmin = this.computeIsAdmin(state);
    this.forceFullscreen = !this.isAdmin;
  }

  private updateYahtecNavState() {
    try {
      const url = this.window.location.pathname;
      this.yahtecOnDashboard = url.includes(YAHTEC_DASHBOARD_ID);
      this.yahtecOnSupervision = url.includes(YAHTEC_SUPERVISION_ID);
      const raw = new URL(this.window.location.href).searchParams.get('state');
      if (!raw) { this.yahtecStateId = 'menu'; return; }
      const arr = JSON.parse(atob(decodeURIComponent(raw)));
      const last = arr[arr.length - 1];
      this.yahtecStateId = (last && last.id) || 'menu';
    } catch {
      this.yahtecStateId = 'menu';
    }
  }

  // Yahtec : navigation vers un state du dashboard
  yahtecNavTo(targetState: YahtecState) {
    const params: any = {};
    if (targetState !== 'menu') {
      // Preserve entityId from current URL state stack
      try {
        const raw = new URL(this.window.location.href).searchParams.get('state');
        if (raw) {
          const arr = JSON.parse(atob(decodeURIComponent(raw)));
          for (let i = arr.length - 1; i >= 0; i--) {
            const p = arr[i] && arr[i].params;
            if (p && p.entityId && p.entityId.id) { params.entityId = p.entityId; break; }
          }
        }
      } catch {}
    }
    const stateB64 = btoa(JSON.stringify([{ id: targetState, params }]));
    // Hard navigation pour garantir l'unmount complet des widgets
    this.window.location.assign(this.window.location.pathname + '?state=' + encodeURIComponent(stateB64));
  }

  // Yahtec : cible du bouton RETOUR selon state
  get yahtecRetourTarget(): YahtecState | null {
    switch (this.yahtecStateId) {
      case 'donnees_HP1':
      case 'depart_chauffage':
      case 'ecs':
      case 'historique':
      case 'configuration':
      case 'profil':
      case 'notifications_admin':
        return 'default';
      case 'fault_diagnostic':
        return 'historique';
      default:
        return null;
    }
  }

  // Yahtec : flags de visibilite des boutons selon le state
  get yahtecShowAccueil(): boolean { return this.yahtecOnDashboard && this.yahtecStateId !== 'menu'; }
  get yahtecShowProfil(): boolean { return this.yahtecOnDashboard && this.yahtecStateId !== 'profil'; }
  get yahtecShowComptes(): boolean {
    return this.yahtecOnDashboard && this.yahtecCanAccessComptes && this.yahtecStateId !== 'notifications_admin';
  }
  get yahtecShowDefaut(): boolean {
    if (!this.yahtecOnDashboard) return false;
    // Defaut visible sur default/donnees_HP1/depart_chauffage/ecs/configuration (pas sur historique/fault_diag/menu)
    return ['default', 'donnees_HP1', 'depart_chauffage', 'ecs', 'configuration'].includes(this.yahtecStateId);
  }
  get yahtecShowParam(): boolean {
    if (!this.yahtecOnDashboard) return false;
    if (!this.yahtecCanAccessComptes) return false; // admin only (configuration = admin)
    return ['default', 'donnees_HP1', 'depart_chauffage', 'ecs', 'historique', 'fault_diagnostic'].includes(this.yahtecStateId);
  }
  get yahtecShowRetour(): boolean {
    return this.yahtecOnDashboard && !!this.yahtecRetourTarget;
  }
  yahtecGoBack() {
    const t = this.yahtecRetourTarget;
    if (t) this.yahtecNavTo(t);
  }

  // Yahtec : retour vers Mes Installations
  yahtecGoToDashboard() {
    this.window.location.assign('/dashboards/' + YAHTEC_DASHBOARD_ID);
  }

  // Yahtec : navigation vers Supervision flotte (admin only)
  yahtecGoToSupervision() {
    this.window.location.assign('/dashboards/' + YAHTEC_SUPERVISION_ID);
  }

  // Yahtec : bouton "Supervision flotte" visible pour les admins, sauf si deja dessus
  get yahtecShowSupervisionBtn(): boolean {
    return this.yahtecCanAccessComptes && !this.yahtecOnSupervision;
  }
  // Yahtec : bouton "Mes Installations" visible quand on est sur Supervision flotte
  get yahtecShowReturnToMesInstallations(): boolean {
    return this.yahtecOnSupervision;
  }

  // Yahtec : deconnexion (utilisee par le bouton custom pour CUSTOMER_USER
  // puisque tb-user-menu est cache pour eux).
  yahtecLogout() {
    this.authService.logout();
  }

  ngOnDestroy() {
    this.window.removeEventListener('popstate', this.yahtecOnPopstate);
    this.destroy$.next();
    this.destroy$.complete();
  }

  ngAfterViewInit() {
    this.textSearch.valueChanges.pipe(
      debounceTime(150),
      startWith(''),
      distinctUntilChanged((a: string, b: string) => a.trim() === b.trim()),
      skip(1),
      takeUntil(this.destroy$)
    ).subscribe(value => this.searchTextUpdated(value.trim()));
  }

  sidenavClicked() {
    if (this.sidenavMode === 'over') {
      this.sidenav.toggle();
    }
  }

  toggleFullscreen() {
    if (screenfull.isEnabled) {
      screenfull.toggle();
    }
  }

  isFullscreen() {
    return screenfull.isFullscreen;
  }

  goBack() {
    this.window.history.back();
  }

  activeComponentChanged(activeComponent: any) {
    this.activeComponentService.setCurrentActiveComponent(activeComponent);
    this.mainContent?.nativeElement?.scrollTo({ top: 0, left: 0 });
    if (!this.activeComponent) {
      setTimeout(() => {
        this.updateActiveComponent(activeComponent);
      }, 0);
    } else {
      this.updateActiveComponent(activeComponent);
    }
  }

  private updateActiveComponent(activeComponent: any) {
    this.showSearch = false;
    this.hideLoadingBar = false;
    this.textSearch.reset('', {emitEvent: false});
    this.activeComponent = activeComponent;

    if (activeComponent && activeComponent instanceof RouterTabsComponent
      && isDefinedAndNotNull(this.activeComponent.activatedRoute?.snapshot?.data?.showMainLoadingBar)) {
      this.hideLoadingBar = !this.activeComponent.activatedRoute.snapshot.data.showMainLoadingBar;
    } else if (activeComponent && activeComponent instanceof PageComponent
      && isDefinedAndNotNull(this.activeComponent?.showMainLoadingBar)) {
      this.hideLoadingBar = !this.activeComponent.showMainLoadingBar;
    }

    if (this.activeComponent && instanceOfSearchableComponent(this.activeComponent)) {
      this.searchEnabled = true;
      this.searchableComponent = this.activeComponent;
    } else {
      this.searchEnabled = false;
      this.searchableComponent = null;
    }
  }

  displaySearchMode(): boolean {
    return this.searchEnabled && this.showSearch;
  }

  openSearch() {
    if (this.searchEnabled) {
      this.showSearch = true;
      setTimeout(() => {
        this.searchInputField.nativeElement.focus();
        this.searchInputField.nativeElement.setSelectionRange(0, 0);
      }, 10);
    }
  }

  closeSearch() {
    if (this.searchEnabled) {
      this.showSearch = false;
      if (this.textSearch.value.length) {
        this.textSearch.reset();
      }
    }
  }

  private searchTextUpdated(searchText: string) {
    if (this.searchableComponent) {
      this.searchableComponent.onSearchTextUpdated(searchText);
    }
  }
}

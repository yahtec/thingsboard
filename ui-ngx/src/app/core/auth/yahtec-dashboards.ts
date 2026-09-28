// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
import { AuthState } from '@core/auth/auth.models';

// Yahtec : identifiants des dashboards TSmart, en un seul endroit. Recopies
// dans home.component.ts et dashboard-routing.module.ts, ils etaient restes sur
// la V1 apres la bascule des clients sur la v2 (2026-09-11) : le bouton
// « Tableau de bord » envoyait alors les clients vers un dashboard qui ne leur
// est plus assigne (403 « Accès interdit »).

// « Mes Installations » V1 : encore ouverte par des comptes internes. La barre
// yahtec (Retour, Défaut, Paramétrage, Accueil, Profil, Comptes) ne connait que ses états.
export const YAHTEC_MES_INSTALLATIONS_V1_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0';

// « Supervision flotte » : reservee aux admins (TENANT_ADMIN ou is_admin=true).
export const YAHTEC_SUPERVISION_ID = '4aa4ccd0-422a-11f1-bbfe-e1395562cba0';

// Dashboard d'atterrissage du compte (additionalInfo.defaultDashboardId) : c'est
// lui que visent « Tableau de bord » et le renvoi hors de Supervision. Aucun
// identifiant en dur : le dashboard client suit chaque compte, et une bascule
// future ne laissera pas de cible perimee dans le code. Il porte sa propre
// navigation (onglets, retour) : la barre yahtec n'y ajoute rien.
export function yahtecLandingDashboardId(state: AuthState): string | null {
  const id = (state?.userDetails?.additionalInfo as Record<string, any>)?.['defaultDashboardId'];
  return typeof id === 'string' && id.length > 0 ? id : null;
}

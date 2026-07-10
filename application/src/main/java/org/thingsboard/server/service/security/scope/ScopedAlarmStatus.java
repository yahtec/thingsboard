/**
 * Copyright © 2016-2026 The Thingsboard Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.thingsboard.server.service.security.scope;

import org.thingsboard.server.common.data.id.CustomerId;

import java.util.Optional;

/**
 * Decision d'autorisation d'une souscription WebSocket au <b>statut d'alarme</b>
 * ({@code AlarmStatusCmd}) en respectant le scope portefeuille (finding I4).
 *
 * <p>Contexte : contrairement aux chemins data ({@code findEntityDataByQueryScoped}) et count
 * ({@link ScopedAlarmCount}), la souscription au statut d'alarme s'abonne directement a
 * {@code cmd.getOriginatorId()} sans passer par une requete scopee. On applique donc ici le meme
 * invariant que le chemin data, au moment de la souscription : on resout le customer proprietaire
 * de l'originator puis on delegue a {@link AccessScope#canView(CustomerId)} :
 * <ul>
 *   <li><b>UNRESTRICTED</b> (TENANT_ADMIN, et tout role resolu unrestricted) : jamais bloque —
 *       comportement upstream inchange (l'appelant ne resout meme pas l'owner).</li>
 *   <li><b>INCLUDE(set)</b> (PARTY, ADMIN_OPS/LEGACY sur leur propre customer) : autorise ssi le
 *       customer de l'originator est dans le portefeuille. Set vide =&gt; deny-by-default.</li>
 *   <li><b>EXCLUDE(set)</b> (STAFF) : autorise ssi le customer de l'originator n'est pas exclu.</li>
 * </ul>
 *
 * <p><b>Fail-closed</b> : si l'owner de l'originator est introuvable (entite supprimee / id
 * inexistant, {@code Optional.empty()}), on refuse pour les users scopes. Le sentinelle
 * {@code NULL_CUSTOMER_ID} (originator non assigne a un customer) est retourne comme un
 * {@code CustomerId} present par {@code entityService.fetchEntityCustomerId} : {@code canView} le
 * traite alors comme n'importe quel customer (refuse en INCLUDE car absent du portefeuille ;
 * accepte en EXCLUDE car absent de l'ensemble exclu — miroir exact du {@code customer_id NOT IN}
 * du chemin data pour les entites tenant-owned).
 */
public final class ScopedAlarmStatus {

    private ScopedAlarmStatus() {
    }

    /**
     * @param scope           scope resolu du user (UNRESTRICTED / INCLUDE / EXCLUDE)
     * @param ownerCustomerId customer proprietaire de l'originator, tel que retourne par
     *                        {@code entityService.fetchEntityCustomerId(...)} ;
     *                        {@code Optional.empty()} =&gt; entite introuvable (fail-closed)
     * @return {@code true} si la souscription au statut d'alarme est autorisee
     */
    public static boolean canSubscribe(AccessScope scope, Optional<CustomerId> ownerCustomerId) {
        if (scope.getMode() == AccessScope.Mode.UNRESTRICTED) {
            return true;
        }
        // User scope : l'originator doit resoudre vers un customer visible ; introuvable => refus.
        return ownerCustomerId.map(scope::canView).orElse(false);
    }
}

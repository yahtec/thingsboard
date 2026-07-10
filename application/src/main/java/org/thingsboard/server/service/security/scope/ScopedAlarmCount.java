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

import java.util.function.ToLongFunction;

/**
 * Algebre de comptage d'alarmes respectant le scope portefeuille pour les requetes SANS entityFilter.
 *
 * <p>Contexte : le chemin data scope ({@code findEntityDataByQueryScoped}) applique, pour les types
 * possedes par un customer (DEVICE/ASSET/ENTITY_VIEW/EDGE), {@code customer_id IN (set)} en INCLUDE et
 * {@code customer_id NOT IN (set)} en EXCLUDE. Les lignes d'alarme portent {@code customer_id} = le
 * customer proprietaire de l'originator. On reproduit donc EXACTEMENT la meme population sans toucher
 * au DAO, en s'appuyant sur le comptage upstream {@code count(a.customer_id = :customerId)} :
 * <ul>
 *   <li><b>INCLUDE(set)</b> : somme des comptes par customer. Les alarmes se partitionnent par
 *       {@code customer_id} (une alarme n'a qu'un seul customer), donc la somme est egale a
 *       {@code count(a.customer_id IN (set))}. Set vide =&gt; 0 (deny-by-default, comme le
 *       {@code 1=0} du chemin data).</li>
 *   <li><b>EXCLUDE(set)</b> : total tenant moins la somme des customers exclus, egal a
 *       {@code count(a.customer_id NOT IN (set))} (les alarmes possedees par le tenant sont
 *       comptees des deux cotes, exactement comme le chemin data qui les inclut). Set vide =&gt;
 *       total tenant.</li>
 * </ul>
 * Le mode UNRESTRICTED n'est PAS gere ici : l'appelant conserve le chemin upstream a l'identique
 * (compteur/table byte-identiques pour TENANT_ADMIN/LEGACY/ADMIN_OPS).
 */
public final class ScopedAlarmCount {

    private ScopedAlarmCount() {
    }

    /**
     * @param scope   scope resolu du user, doit etre INCLUDE ou EXCLUDE
     *                (UNRESTRICTED est gere par l'appelant)
     * @param counter fonction de comptage adossee au DAO :
     *                {@code customerId} non-null =&gt; {@code count(a.customer_id = customerId)} ;
     *                {@code customerId} null =&gt; comptage tenant-wide (aucun filtre customer)
     * @return le nombre d'alarmes visibles dans le scope
     */
    public static long countFilterless(AccessScope scope, ToLongFunction<CustomerId> counter) {
        switch (scope.getMode()) {
            case INCLUDE: {
                long total = 0;
                for (CustomerId customerId : scope.getCustomers()) {
                    total += counter.applyAsLong(customerId);
                }
                return total;
            }
            case EXCLUDE: {
                long total = counter.applyAsLong(null);
                for (CustomerId customerId : scope.getCustomers()) {
                    total -= counter.applyAsLong(customerId);
                }
                return Math.max(total, 0);
            }
            default:
                // Fail-closed : l'appelant ne doit jamais router UNRESTRICTED ici.
                throw new IllegalArgumentException(
                        "countFilterless ne gere pas le mode " + scope.getMode());
        }
    }
}

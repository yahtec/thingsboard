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

import lombok.extern.slf4j.Slf4j;
import org.thingsboard.server.common.data.id.CustomerId;

import java.util.Collection;
import java.util.Set;
import java.util.function.Supplier;
import java.util.function.ToLongFunction;

/**
 * Algebre de comptage d'alarmes respectant le scope portefeuille pour les requetes SANS entityFilter.
 *
 * <p>Contexte : le chemin data scope ({@code findEntityDataByQueryScoped}) applique, pour les types
 * possedes par un customer (DEVICE/ASSET/ENTITY_VIEW/EDGE), {@code customer_id IN (set)} en INCLUDE et
 * {@code customer_id NOT IN (set)} en EXCLUDE. Les lignes d'alarme portent {@code customer_id} = le
 * customer proprietaire de l'originator. On reproduit donc la meme population sans toucher au DAO, en
 * s'appuyant sur le comptage upstream {@code count(a.customer_id = :customerId)} :
 * <ul>
 *   <li><b>INCLUDE(set)</b> : somme des comptes par customer. Les alarmes se partitionnent par
 *       {@code customer_id} (une alarme n'a qu'un seul customer), donc la somme est egale a
 *       {@code count(a.customer_id IN (set))}. Set vide =&gt; 0 (deny-by-default, comme le
 *       {@code 1=0} du chemin data).</li>
 *   <li><b>EXCLUDE(set)</b> : on enumere les customers <b>visibles</b> du tenant (tous les customers
 *       moins l'ensemble exclu) et on somme leurs comptes, exactement comme INCLUDE(tous - exclus).
 *       On <b>ne</b> calcule <b>plus</b> {@code total tenant - exclus} : le total tenant compterait
 *       les alarmes possedees par le tenant (originator non assigne), qui portent le customer_id
 *       <em>sentinelle</em> {@code NULL_CUSTOMER_ID} — un vrai UUID que la boucle de soustraction ne
 *       retire jamais (le garde DAO {@code customerId != null && !isNullUid()} traite la sentinelle
 *       comme « pas de filtre » =&gt; comptage tenant-wide). Le chemin data, lui, exclut ces lignes
 *       car un device non assigne a {@code customer_id} SQL NULL (drop par {@code NOT IN}). En
 *       comptant par customers visibles, la sentinelle/NULL est exclue <b>par construction</b> des
 *       deux cotes. Set vide =&gt; tous les customers.</li>
 * </ul>
 * Le mode UNRESTRICTED n'est PAS gere ici : l'appelant conserve le chemin upstream a l'identique
 * (compteur/table byte-identiques pour TENANT_ADMIN/LEGACY/ADMIN_OPS).
 */
@Slf4j
public final class ScopedAlarmCount {

    private ScopedAlarmCount() {
    }

    /**
     * @param scope           scope resolu du user, doit etre INCLUDE ou EXCLUDE
     *                        (UNRESTRICTED est gere par l'appelant)
     * @param counter         fonction de comptage adossee au DAO :
     *                        {@code count(a.customer_id = customerId)} (customerId non-null)
     * @param tenantCustomers fournit l'ensemble des customers du tenant ; invoque UNIQUEMENT en
     *                        EXCLUDE (paresseux). En cas d'echec, on <b>fail-closed a 0</b> (+WARN).
     * @return le nombre d'alarmes visibles dans le scope
     */
    public static long countFilterless(AccessScope scope, ToLongFunction<CustomerId> counter,
                                        Supplier<Collection<CustomerId>> tenantCustomers) {
        switch (scope.getMode()) {
            case INCLUDE: {
                long total = 0;
                for (CustomerId customerId : scope.getCustomers()) {
                    total += counter.applyAsLong(customerId);
                }
                return total;
            }
            case EXCLUDE: {
                // On compte par customers VISIBLES = INCLUDE(tous les customers du tenant - exclus).
                // On ne calcule plus `total tenant - exclus` : le total tenant compterait les alarmes
                // tenant-owned (sentinelle NULL_CUSTOMER_ID), que la boucle de soustraction ne retire
                // jamais. En sommant seulement les customers reels non exclus, la sentinelle/NULL est
                // exclue par construction, exactement comme le `customer_id NOT IN (:ids)` du chemin data.
                Collection<CustomerId> allCustomers;
                try {
                    allCustomers = tenantCustomers.get();
                } catch (RuntimeException e) {
                    // Fail-closed (0) : on ne peut pas enumerer le perimetre visible, on ne divulgue rien.
                    log.warn("Echec de l'enumeration des customers du tenant pour un comptage EXCLUDE ;"
                            + " fail-closed a 0", e);
                    return 0;
                }
                Set<CustomerId> excluded = scope.getCustomers();
                long total = 0;
                for (CustomerId customerId : allCustomers) {
                    if (customerId != null && !excluded.contains(customerId)) {
                        total += counter.applyAsLong(customerId);
                    }
                }
                return total;
            }
            default:
                // Fail-closed : l'appelant ne doit jamais router UNRESTRICTED ici.
                throw new IllegalArgumentException(
                        "countFilterless ne gere pas le mode " + scope.getMode());
        }
    }
}

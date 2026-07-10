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

import org.junit.jupiter.api.Test;
import org.thingsboard.server.common.data.id.CustomerId;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Supplier;
import java.util.function.ToLongFunction;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Teste l'algebre de comptage scope pour les requetes d'alarme SANS entityFilter.
 *
 * <p>Le compteur simule le DAO : {@code count(a.customer_id = customerId)}. En EXCLUDE, le nouvel
 * algorithme compte par <b>customers visibles</b> (= tous les customers du tenant moins l'ensemble
 * exclu) — il ne calcule PLUS {@code total tenant - exclus}. Le compteur leve donc une AssertionError
 * s'il est interroge avec {@code null} (tenant-wide) : ce chemin comptait la sentinelle tenant-owned
 * {@code NULL_CUSTOMER_ID} et cassait l'invariant compteur ≡ table.
 */
class ScopedAlarmCountTest {

    private final CustomerId siteA = new CustomerId(UUID.randomUUID());
    private final CustomerId siteB = new CustomerId(UUID.randomUUID());
    private final CustomerId siteC = new CustomerId(UUID.randomUUID());

    /** Compteur par customer ; leve si on l'appelle avec null (le total tenant ne doit jamais servir). */
    private static ToLongFunction<CustomerId> counter(Map<CustomerId, Long> perCustomer) {
        return cid -> {
            if (cid == null) {
                throw new AssertionError("le total tenant-wide (customerId=null) ne doit jamais etre interroge");
            }
            return perCustomer.getOrDefault(cid, 0L);
        };
    }

    /** Enumeration des customers du tenant ; leve si invoquee (utile pour prouver le non-appel en INCLUDE). */
    private static Supplier<Collection<CustomerId>> customersNeverCalled() {
        return () -> {
            throw new AssertionError("l'enumeration des customers ne doit pas etre invoquee en INCLUDE");
        };
    }

    @Test
    void includeSumsPerCustomerCounts() {
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.include(Set.of(siteA, siteB)),
                counter(Map.of(siteA, 3L, siteB, 4L)),
                customersNeverCalled());
        assertThat(result).isEqualTo(7L);
    }

    @Test
    void includeEmptyIsDenyByDefault() {
        // Set INCLUDE vide => 0, et ni le compteur ni l'enumeration des customers ne doivent etre touches.
        List<CustomerId> calls = new ArrayList<>();
        ToLongFunction<CustomerId> spy = cid -> {
            calls.add(cid);
            return 1234L;
        };
        long result = ScopedAlarmCount.countFilterless(AccessScope.include(Set.of()), spy, customersNeverCalled());
        assertThat(result).isZero();
        assertThat(calls).isEmpty();
    }

    @Test
    void excludeCountsVisibleCustomersNotExcluded() {
        // Tenant = {A, B, C} ; exclu = {C} => on compte A + B, jamais C, jamais le total tenant.
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of(siteC)),
                counter(Map.of(siteA, 5L, siteB, 6L, siteC, 100L)),
                () -> List.of(siteA, siteB, siteC));
        assertThat(result).isEqualTo(11L);
    }

    @Test
    void excludeEmptyCountsAllTenantCustomers() {
        // exclu vide => somme de tous les customers du tenant (jamais via le total tenant-wide).
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of()),
                counter(Map.of(siteA, 20L, siteB, 22L)),
                () -> List.of(siteA, siteB));
        assertThat(result).isEqualTo(42L);
    }

    @Test
    void excludeNeverCountsSentinelTenantBucket() {
        // Reproduit le finding : sous l'ancienne algebre, total tenant = 7 (A=2 + B=3 + sentinelle=2)
        // puis - exclus => la sentinelle tenant-owned restait comptee. La nouvelle algebre somme les
        // customers visibles {A, B} = 5 et n'interroge JAMAIS le total tenant (compteur(null) => leve).
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of(siteC)),
                counter(Map.of(siteA, 2L, siteB, 3L, siteC, 99L)),
                () -> List.of(siteA, siteB, siteC));
        assertThat(result).isEqualTo(5L);
    }

    @Test
    void excludeFailsClosedWhenCustomerListingFails() {
        // Echec de l'enumeration des customers => fail-closed a 0 (on ne compte rien).
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of(siteC)),
                counter(Map.of(siteA, 5L)),
                () -> {
                    throw new RuntimeException("DB down");
                });
        assertThat(result).isZero();
    }
}

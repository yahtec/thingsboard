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
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.ToLongFunction;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Teste l'algebre de comptage scope pour les requetes d'alarme SANS entityFilter.
 * Le compteur simule le DAO : customerId non-null => count(a.customer_id = customerId) ;
 * customerId null => count tenant-wide.
 */
class ScopedAlarmCountTest {

    private final CustomerId siteA = new CustomerId(UUID.randomUUID());
    private final CustomerId siteB = new CustomerId(UUID.randomUUID());

    /** Compteur mimant le DAO : la valeur pour null (tenant-wide) est la somme de tous les customers. */
    private static ToLongFunction<CustomerId> counter(long tenantTotal, Map<CustomerId, Long> perCustomer) {
        List<CustomerId> calls = new ArrayList<>();
        return cid -> {
            calls.add(cid);
            return cid == null ? tenantTotal : perCustomer.getOrDefault(cid, 0L);
        };
    }

    @Test
    void includeSumsPerCustomerCounts() {
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.include(Set.of(siteA, siteB)),
                counter(999L, Map.of(siteA, 3L, siteB, 4L)));
        assertThat(result).isEqualTo(7L);
    }

    @Test
    void includeEmptyIsDenyByDefault() {
        // Set INCLUDE vide => 0, et le compteur ne doit JAMAIS toucher le tenant-wide.
        List<CustomerId> calls = new ArrayList<>();
        ToLongFunction<CustomerId> spy = cid -> {
            calls.add(cid);
            return 1234L;
        };
        long result = ScopedAlarmCount.countFilterless(AccessScope.include(Set.of()), spy);
        assertThat(result).isZero();
        assertThat(calls).isEmpty();
    }

    @Test
    void excludeIsTenantTotalMinusExcluded() {
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of(siteA, siteB)),
                counter(20L, Map.of(siteA, 5L, siteB, 6L)));
        assertThat(result).isEqualTo(20L - 5L - 6L);
    }

    @Test
    void excludeEmptyIsTenantTotal() {
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of()),
                counter(42L, Map.of()));
        assertThat(result).isEqualTo(42L);
    }

    @Test
    void excludeNeverGoesNegative() {
        // Race/incoherence : la somme des exclus depasse le total tenant lu a un instant different.
        long result = ScopedAlarmCount.countFilterless(
                AccessScope.exclude(Set.of(siteA)),
                counter(2L, Map.of(siteA, 5L)));
        assertThat(result).isZero();
    }
}

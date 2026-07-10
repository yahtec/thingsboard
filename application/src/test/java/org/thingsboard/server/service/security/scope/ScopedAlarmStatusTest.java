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
import org.thingsboard.server.common.data.id.EntityId;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Teste la decision d'autorisation d'une souscription WebSocket au statut d'alarme (finding I4).
 *
 * <p>Rappel du bug : {@code handleCmd(AlarmStatusCmd)} ouvrait une souscription sur
 * {@code cmd.getOriginatorId()} sans aucun controle de scope ; un PARTY recevait donc le statut
 * d'alarme live de n'importe quel device du tenant. La decision extraite ici est le miroir du
 * chemin data/count : UNRESTRICTED inchange, INCLUDE/EXCLUDE routes via {@link AccessScope#canView},
 * originator introuvable => fail-closed.
 */
class ScopedAlarmStatusTest {

    private final CustomerId siteA = new CustomerId(UUID.randomUUID());
    private final CustomerId siteB = new CustomerId(UUID.randomUUID());
    // Sentinelle NULL_CUSTOMER_ID (originator tenant-owned/non assigne) : c'est ce que retourne
    // entityService.fetchEntityCustomerId(...) pour un device dont customer_id est SQL NULL en base
    // (BaseEntityService.getCustomerId mappe null -> NULL_CUSTOMER_ID, jamais Optional.empty()).
    private final CustomerId sentinel = new CustomerId(EntityId.NULL_UUID);

    @Test
    void unrestrictedAlwaysAllowedEvenWhenOwnerResolved() {
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.unrestricted(), Optional.of(siteA))).isTrue();
    }

    @Test
    void unrestrictedAlwaysAllowedEvenWhenOwnerUnresolved() {
        // TENANT_ADMIN : inchange, on ne bloque jamais meme si l'originator est introuvable.
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.unrestricted(), Optional.empty())).isTrue();
    }

    @Test
    void includeAllowsOriginatorOwnedByPortfolioCustomer() {
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.include(Set.of(siteA, siteB)), Optional.of(siteA))).isTrue();
    }

    @Test
    void includeRefusesOriginatorOutsidePortfolio() {
        // Le coeur du fix : PARTY sur un device d'un autre customer => refus.
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.include(Set.of(siteA)), Optional.of(siteB))).isFalse();
    }

    @Test
    void includeEmptyPortfolioRefusesEverything() {
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.include(Set.of()), Optional.of(siteA))).isFalse();
    }

    @Test
    void includeFailsClosedWhenOriginatorUnresolved() {
        // Originator introuvable (entite supprimee / id inexistant) => refus (fail-closed).
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.include(Set.of(siteA)), Optional.empty())).isFalse();
    }

    @Test
    void excludeAllowsOriginatorNotExcluded() {
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.exclude(Set.of(siteA)), Optional.of(siteB))).isTrue();
    }

    @Test
    void excludeRefusesOriginatorOwnedByExcludedCustomer() {
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.exclude(Set.of(siteA)), Optional.of(siteA))).isFalse();
    }

    @Test
    void excludeFailsClosedWhenOriginatorUnresolved() {
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.exclude(Set.of(siteA)), Optional.empty())).isFalse();
    }

    @Test
    void excludeRefusesOriginatorOwnedBySentinel() {
        // Coeur du fix : un originator tenant-owned (customer_id SQL NULL en base) resout vers la
        // sentinelle NULL_CUSTOMER_ID, jamais Optional.empty(). Le chemin data (customer_id NOT IN)
        // et ScopedAlarmCount (somme par customers reels) DROPPENT ces lignes ; le statut d'alarme
        // doit donc refuser aussi, meme en EXCLUDE ou la sentinelle serait "absente de l'ensemble
        // exclu" si elle etait traitee comme un customer normal.
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.exclude(Set.of(siteA)), Optional.of(sentinel))).isFalse();
    }

    @Test
    void includeRefusesOriginatorOwnedBySentinel() {
        // Deja refuse avant le fix (sentinelle absente du portefeuille) ; on l'epingle explicitement.
        assertThat(ScopedAlarmStatus.canSubscribe(AccessScope.include(Set.of(siteA)), Optional.of(sentinel))).isFalse();
    }
}

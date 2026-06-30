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

import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class AccessScopeTest {

    private final CustomerId a = new CustomerId(UUID.randomUUID());
    private final CustomerId b = new CustomerId(UUID.randomUUID());

    @Test
    void unrestrictedSeesEverythingIncludingNull() {
        AccessScope scope = AccessScope.unrestricted();
        assertThat(scope.canView(a)).isTrue();
        assertThat(scope.canView(null)).isTrue();
    }

    @Test
    void includeSeesOnlyListed() {
        AccessScope scope = AccessScope.include(Set.of(a));
        assertThat(scope.canView(a)).isTrue();
        assertThat(scope.canView(b)).isFalse();
    }

    @Test
    void emptyIncludeDeniesEverything() {
        AccessScope scope = AccessScope.include(Set.of());
        assertThat(scope.canView(a)).isFalse();
        assertThat(scope.canView(null)).isFalse();
    }

    @Test
    void excludeSeesAllButListed() {
        AccessScope scope = AccessScope.exclude(Set.of(a));
        assertThat(scope.canView(a)).isFalse();
        assertThat(scope.canView(b)).isTrue();
        assertThat(scope.canView(null)).isFalse();
    }

    @Test
    void customerUuidsInclude() {
        AccessScope scope = AccessScope.include(Set.of(a, b));
        assertThat(scope.customerUuids()).containsExactlyInAnyOrder(a.getId(), b.getId());
    }

    @Test
    void customerUuidsExclude() {
        AccessScope scope = AccessScope.exclude(Set.of(a));
        assertThat(scope.customerUuids()).containsExactly(a.getId());
    }
}

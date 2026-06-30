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

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.thingsboard.common.util.JacksonUtil;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.relation.RelationService;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.user.cache.UserAuthDetailsCache;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultAccessScopeServiceTest {

    @Mock
    RelationService relationService;

    @Mock
    UserAuthDetailsCache userAuthDetailsCache;

    DefaultAccessScopeService service;

    final TenantId tenantId = new TenantId(UUID.randomUUID());

    @BeforeEach
    void setUp() {
        service = new DefaultAccessScopeService(relationService, userAuthDetailsCache);
    }

    private SecurityUser user(Authority authority, CustomerId customerId, String role) {
        SecurityUser u = new SecurityUser(new UserId(UUID.randomUUID()));
        u.setAuthority(authority);
        u.setTenantId(tenantId);
        u.setCustomerId(customerId);
        if (role != null) {
            ObjectNode info = JacksonUtil.newObjectNode();
            info.put(PortfolioAccess.ROLE_FIELD, role);
            u.setAdditionalInfo(info);
        }
        return u;
    }

    private EntityRelation rel(CustomerId from, CustomerId to, String type) {
        return new EntityRelation(from, to, type, PortfolioAccess.RELATION_GROUP);
    }

    @Test
    void tenantAdminIsUnrestricted() {
        SecurityUser admin = user(Authority.TENANT_ADMIN, null, null);
        assertThat(service.resolve(admin).getMode()).isEqualTo(AccessScope.Mode.UNRESTRICTED);
    }

    @Test
    void partySeesOnlyCanViewTargets() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        CustomerId site1 = new CustomerId(UUID.randomUUID());
        CustomerId other = new CustomerId(UUID.randomUUID());
        when(relationService.findByFromAndType(tenantId, party, PortfolioAccess.CAN_VIEW, PortfolioAccess.RELATION_GROUP))
                .thenReturn(List.of(rel(party, site1, PortfolioAccess.CAN_VIEW)));

        SecurityUser u = user(Authority.CUSTOMER_USER, party, "PARTY");
        assertThat(service.canView(u, site1)).isTrue();
        assertThat(service.canView(u, other)).isFalse();
    }

    @Test
    void partyWithNoRelationsSeesNothing() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        when(relationService.findByFromAndType(eq(tenantId), eq(party), eq(PortfolioAccess.CAN_VIEW), any()))
                .thenReturn(List.of());
        SecurityUser u = user(Authority.CUSTOMER_USER, party, "PARTY");
        assertThat(service.canView(u, new CustomerId(UUID.randomUUID()))).isFalse();
    }

    @Test
    void staffSeesAllButExcluded() {
        CustomerId staff = new CustomerId(UUID.randomUUID());
        CustomerId excluded = new CustomerId(UUID.randomUUID());
        CustomerId visible = new CustomerId(UUID.randomUUID());
        when(relationService.findByFromAndType(tenantId, staff, PortfolioAccess.EXCLUDED, PortfolioAccess.RELATION_GROUP))
                .thenReturn(List.of(rel(staff, excluded, PortfolioAccess.EXCLUDED)));

        SecurityUser u = user(Authority.CUSTOMER_USER, staff, "STAFF");
        assertThat(service.canView(u, excluded)).isFalse();
        assertThat(service.canView(u, visible)).isTrue();
    }

    @Test
    void legacyCustomerUserSeesOnlyOwnCustomer() {
        CustomerId own = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, own, null);
        assertThat(service.canView(u, own)).isTrue();
        assertThat(service.canView(u, new CustomerId(UUID.randomUUID()))).isFalse();
    }

    @Test
    void tenantAdminIsNotReadOnly() {
        assertThat(service.isReadOnly(user(Authority.TENANT_ADMIN, null, null))).isFalse();
    }

    @Test
    void partyIsReadOnly() {
        assertThat(service.isReadOnly(user(Authority.CUSTOMER_USER, new CustomerId(UUID.randomUUID()), "PARTY"))).isTrue();
    }

    @Test
    void staffIsReadOnly() {
        assertThat(service.isReadOnly(user(Authority.CUSTOMER_USER, new CustomerId(UUID.randomUUID()), "STAFF"))).isTrue();
    }

    @Test
    void legacyCustomerUserIsNotReadOnly() {
        assertThat(service.isReadOnly(user(Authority.CUSTOMER_USER, new CustomerId(UUID.randomUUID()), null))).isFalse();
    }

    @Test
    void scopeIsCachedThenInvalidated() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        when(relationService.findByFromAndType(eq(tenantId), eq(party), eq(PortfolioAccess.CAN_VIEW), any()))
                .thenReturn(List.of());
        SecurityUser u = user(Authority.CUSTOMER_USER, party, "PARTY");

        service.resolve(u);
        service.resolve(u);
        verify(relationService, times(1)).findByFromAndType(eq(tenantId), eq(party), eq(PortfolioAccess.CAN_VIEW), any());

        service.invalidate(party);
        service.resolve(u);
        verify(relationService, times(2)).findByFromAndType(eq(tenantId), eq(party), eq(PortfolioAccess.CAN_VIEW), any());
    }

    // ── I2 : la cle de cache est composite (customerId, role) ────────────────────────────
    //
    // Avant le fix, le cache etait keye sur customerId seul → deux users du MEME customer mais de
    // roles differents (ex. PARTY vs STAFF) partageaient l'entree, et le premier resolu imposait
    // son scope au second. Apres le fix, chaque (customer, role) a sa propre entree.

    @Test
    void sameCustomerDifferentRolesGetDistinctScopes() {
        CustomerId customer = new CustomerId(UUID.randomUUID());
        CustomerId site = new CustomerId(UUID.randomUUID());
        CustomerId excluded = new CustomerId(UUID.randomUUID());

        when(relationService.findByFromAndType(tenantId, customer, PortfolioAccess.CAN_VIEW, PortfolioAccess.RELATION_GROUP))
                .thenReturn(List.of(rel(customer, site, PortfolioAccess.CAN_VIEW)));
        when(relationService.findByFromAndType(tenantId, customer, PortfolioAccess.EXCLUDED, PortfolioAccess.RELATION_GROUP))
                .thenReturn(List.of(rel(customer, excluded, PortfolioAccess.EXCLUDED)));

        SecurityUser party = user(Authority.CUSTOMER_USER, customer, "PARTY");
        SecurityUser staff = user(Authority.CUSTOMER_USER, customer, "STAFF");

        // PARTY resolu d'abord : INCLUDE {site}
        AccessScope partyScope = service.resolve(party);
        assertThat(partyScope.getMode()).isEqualTo(AccessScope.Mode.INCLUDE);

        // STAFF (meme customer) ne doit PAS heriter de l'entree PARTY mise en cache
        AccessScope staffScope = service.resolve(staff);
        assertThat(staffScope.getMode()).isEqualTo(AccessScope.Mode.EXCLUDE);

        // Verification croisee : PARTY voit le site et pas l'exclu ; STAFF l'inverse
        assertThat(service.canView(party, site)).isTrue();
        assertThat(service.canView(party, excluded)).isFalse();
        assertThat(service.canView(staff, excluded)).isFalse();
        assertThat(service.canView(staff, site)).isTrue();
    }

    @Test
    void invalidatePurgesAllRolesOfCustomer() {
        CustomerId customer = new CustomerId(UUID.randomUUID());
        when(relationService.findByFromAndType(eq(tenantId), eq(customer), eq(PortfolioAccess.CAN_VIEW), any()))
                .thenReturn(List.of());
        when(relationService.findByFromAndType(eq(tenantId), eq(customer), eq(PortfolioAccess.EXCLUDED), any()))
                .thenReturn(List.of());

        SecurityUser party = user(Authority.CUSTOMER_USER, customer, "PARTY");
        SecurityUser staff = user(Authority.CUSTOMER_USER, customer, "STAFF");

        service.resolve(party);
        service.resolve(staff);
        verify(relationService, times(1)).findByFromAndType(eq(tenantId), eq(customer), eq(PortfolioAccess.CAN_VIEW), any());
        verify(relationService, times(1)).findByFromAndType(eq(tenantId), eq(customer), eq(PortfolioAccess.EXCLUDED), any());

        // Une seule invalidation doit purger LES DEUX entrees (PARTY et STAFF) de ce customer
        service.invalidate(customer);

        service.resolve(party);
        service.resolve(staff);
        verify(relationService, times(2)).findByFromAndType(eq(tenantId), eq(customer), eq(PortfolioAccess.CAN_VIEW), any());
        verify(relationService, times(2)).findByFromAndType(eq(tenantId), eq(customer), eq(PortfolioAccess.EXCLUDED), any());
    }
}

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
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.thingsboard.server.common.data.Customer;
import org.thingsboard.server.common.data.User;
import org.thingsboard.server.common.data.audit.ActionType;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.EntityId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.common.data.relation.RelationTypeGroup;
import org.thingsboard.server.dao.eventsourcing.RelationActionEvent;
import org.thingsboard.server.dao.eventsourcing.SaveEntityEvent;

import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class ScopeCacheInvalidationListenerTest {

    @Mock
    private AccessScopeService accessScopeService;

    @InjectMocks
    private ScopeCacheInvalidationListener listener;

    private final TenantId tenantId = new TenantId(UUID.randomUUID());
    private final CustomerId customerA = new CustomerId(UUID.randomUUID());
    private final CustomerId customerB = new CustomerId(UUID.randomUUID());

    // ── RelationActionEvent ──────────────────────────────────────────────────

    @Test
    void canViewRelationInvalidatesFromCustomer() {
        EntityRelation rel = canViewRelation(customerA, customerB);
        listener.handleRelationEvent(new RelationActionEvent(tenantId, rel, ActionType.RELATION_ADD_OR_UPDATE));
        verify(accessScopeService).invalidate(customerA);
    }

    @Test
    void excludedRelationInvalidatesFromCustomer() {
        EntityRelation rel = excludedRelation(customerA, customerB);
        listener.handleRelationEvent(new RelationActionEvent(tenantId, rel, ActionType.RELATION_DELETED));
        verify(accessScopeService).invalidate(customerA);
    }

    @Test
    void unrelatedRelationTypeDoesNotInvalidate() {
        EntityRelation rel = new EntityRelation();
        rel.setFrom(customerA);
        rel.setTo(customerB);
        rel.setType("Contains");
        rel.setTypeGroup(RelationTypeGroup.COMMON);
        listener.handleRelationEvent(new RelationActionEvent(tenantId, rel, ActionType.RELATION_ADD_OR_UPDATE));
        verify(accessScopeService, never()).invalidate(any());
        verify(accessScopeService, never()).invalidateAll();
    }

    @Test
    void nullRelationDoesNothing() {
        listener.handleRelationEvent(new RelationActionEvent(tenantId, null, ActionType.RELATION_ADD_OR_UPDATE));
        verify(accessScopeService, never()).invalidate(any());
        verify(accessScopeService, never()).invalidateAll();
    }

    @Test
    void nonCustomerFromDoesNotInvalidate() {
        // from = Device (not a Customer) — should be ignored
        EntityRelation rel = new EntityRelation();
        org.thingsboard.server.common.data.id.DeviceId deviceId =
                new org.thingsboard.server.common.data.id.DeviceId(UUID.randomUUID());
        rel.setFrom(deviceId);
        rel.setTo(customerB);
        rel.setType(PortfolioAccess.CAN_VIEW);
        rel.setTypeGroup(RelationTypeGroup.COMMON);
        listener.handleRelationEvent(new RelationActionEvent(tenantId, rel, ActionType.RELATION_ADD_OR_UPDATE));
        verify(accessScopeService, never()).invalidate(any());
    }

    // ── SaveEntityEvent<User> ────────────────────────────────────────────────

    @Test
    void userSaveInvalidatesCustomer() {
        User user = buildUser(customerA);
        SaveEntityEvent<User> event = SaveEntityEvent.<User>builder()
                .tenantId(tenantId).entity(user).entityId(user.getId()).build();
        listener.handleUserSaveEvent(event);
        verify(accessScopeService).invalidate(customerA);
    }

    @Test
    void userSaveWithNullCustomerIdDoesNothing() {
        User user = buildUser(null);
        SaveEntityEvent<User> event = SaveEntityEvent.<User>builder()
                .tenantId(tenantId).entity(user).entityId(user.getId()).build();
        listener.handleUserSaveEvent(event);
        verify(accessScopeService, never()).invalidate(any());
    }

    @Test
    void userSaveWithNullEntityDoesNothing() {
        // entity field is null — instanceof guard should prevent any invalidation
        SaveEntityEvent<User> event = SaveEntityEvent.<User>builder()
                .tenantId(tenantId).entity(null).entityId(new UserId(UUID.randomUUID())).build();
        listener.handleUserSaveEvent(event);
        verify(accessScopeService, never()).invalidate(any());
    }

    @Test
    void saveEventWithNonUserEntityDoesNothing() {
        // Le handler est désormais typé SaveEntityEvent<?> (fix generics I1) :
        // un évènement portant une entité non-User doit être ignoré.
        Customer customer = new Customer(customerA);
        SaveEntityEvent<Customer> event = SaveEntityEvent.<Customer>builder()
                .tenantId(tenantId).entity(customer).entityId(customer.getId()).build();
        listener.handleUserSaveEvent(event);
        verify(accessScopeService, never()).invalidate(any());
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    private static EntityRelation canViewRelation(EntityId from, EntityId to) {
        EntityRelation rel = new EntityRelation();
        rel.setFrom(from);
        rel.setTo(to);
        rel.setType(PortfolioAccess.CAN_VIEW);
        rel.setTypeGroup(RelationTypeGroup.COMMON);
        return rel;
    }

    private static EntityRelation excludedRelation(EntityId from, EntityId to) {
        EntityRelation rel = new EntityRelation();
        rel.setFrom(from);
        rel.setTo(to);
        rel.setType(PortfolioAccess.EXCLUDED);
        rel.setTypeGroup(RelationTypeGroup.COMMON);
        return rel;
    }

    private static User buildUser(CustomerId customerId) {
        User user = new User();
        user.setId(new UserId(UUID.randomUUID()));
        user.setCustomerId(customerId);
        return user;
    }
}

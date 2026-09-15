// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.dao.entity;

import com.google.common.util.concurrent.FluentFuture;
import com.google.common.util.concurrent.ListenableFuture;
import org.thingsboard.server.common.data.EntityInfo;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.EntityId;
import org.thingsboard.server.common.data.id.HasId;
import org.thingsboard.server.common.data.id.NameLabelAndCustomerDetails;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.page.PageData;
import org.thingsboard.server.common.data.permission.CustomerScopeMode;
import org.thingsboard.server.common.data.query.EntityCountQuery;
import org.thingsboard.server.common.data.query.EntityData;
import org.thingsboard.server.common.data.query.EntityDataQuery;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public interface EntityService {

    Optional<String> fetchEntityName(TenantId tenantId, EntityId entityId);

    Optional<String> fetchEntityLabel(TenantId tenantId, EntityId entityId);

    Optional<CustomerId> fetchEntityCustomerId(TenantId tenantId, EntityId entityId);

    FluentFuture<Optional<CustomerId>> fetchEntityCustomerIdAsync(TenantId tenantId, EntityId entityId);

    Optional<HasId<?>> fetchEntity(TenantId tenantId, EntityId entityId);

    Map<EntityId, EntityInfo> fetchEntityInfos(TenantId tenantId, CustomerId customerId, Set<EntityId> entityIds);

    Optional<NameLabelAndCustomerDetails> fetchNameLabelAndCustomerDetails(TenantId tenantId, EntityId entityId);

    long countEntitiesByQuery(TenantId tenantId, CustomerId customerId, EntityCountQuery query);

    PageData<EntityData> findEntityDataByQuery(TenantId tenantId, CustomerId customerId, EntityDataQuery query);

    ListenableFuture<PageData<EntityData>> findEntityDataByQueryAsync(TenantId tenantId, CustomerId customerId, EntityDataQuery query);

    long countEntitiesByQueryScoped(TenantId tenantId, CustomerId ownCustomerId, List<UUID> customerIds, CustomerScopeMode scopeMode, EntityCountQuery query);

    PageData<EntityData> findEntityDataByQueryScoped(TenantId tenantId, CustomerId ownCustomerId, List<UUID> customerIds, CustomerScopeMode scopeMode, EntityDataQuery query);

    ListenableFuture<PageData<EntityData>> findEntityDataByQueryScopedAsync(TenantId tenantId, CustomerId ownCustomerId, List<UUID> customerIds, CustomerScopeMode scopeMode, EntityDataQuery query);

}

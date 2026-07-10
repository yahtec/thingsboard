/**
 * Copyright © 2016-2024 The Thingsboard Authors
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
package org.thingsboard.server.common.data.permission;

import lombok.Getter;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class QueryContext {

    @Getter
    private final TenantId tenantId;
    @Getter
    private final CustomerId customerId;
    @Getter
    private final EntityType entityType;
    @Getter
    private final boolean ignorePermissionCheck;
    @Getter
    private final List<UUID> customerIds;
    @Getter
    private final CustomerScopeMode scopeMode;

    @Getter
    private final Map<UUID, UUID> relatedParentIdMap = new HashMap<>();

    public QueryContext(TenantId tenantId, CustomerId customerId, EntityType entityType) {
        this(tenantId, customerId, entityType, false);
    }

    public QueryContext(TenantId tenantId, CustomerId customerId, EntityType entityType, boolean ignorePermissionCheck) {
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.entityType = entityType;
        this.ignorePermissionCheck = ignorePermissionCheck;
        this.customerIds = null;
        this.scopeMode = CustomerScopeMode.UNRESTRICTED;
    }

    /**
     * Scoped constructor that ALSO carries the querying user's own customerId.
     *
     * <p>The portfolio scope ({@code customerIds} + {@code scopeMode}) is applied only to the
     * customer-owned entity types ({@code DEVICE/ASSET/ENTITY_VIEW/EDGE}); for every other entity
     * type the repository falls back to the legacy own-customer filter, which relies on
     * {@link #getCustomerId()}. Storing the own customerId here keeps that fallback safe
     * (equivalent to a non-scoped customer user) instead of leaking tenant-wide.
     */
    public QueryContext(TenantId tenantId, CustomerId ownCustomerId, EntityType entityType, List<UUID> customerIds, CustomerScopeMode scopeMode) {
        this.tenantId = tenantId;
        this.customerId = ownCustomerId;
        this.entityType = entityType;
        this.ignorePermissionCheck = false;
        this.customerIds = customerIds;
        this.scopeMode = scopeMode;
    }

    public boolean isTenantUser() {
        return customerId == null || customerId.isNullUid();
    }
}
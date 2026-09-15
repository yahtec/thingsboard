// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.dao.sql.query;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.page.PageData;
import org.thingsboard.server.common.data.permission.CustomerScopeMode;
import org.thingsboard.server.common.data.query.EntityCountQuery;
import org.thingsboard.server.common.data.query.EntityData;
import org.thingsboard.server.common.data.query.EntityDataQuery;
import org.thingsboard.server.dao.entity.EntityQueryDao;

import java.util.List;
import java.util.UUID;

@Component
public class JpaEntityQueryDao implements EntityQueryDao {

    @Autowired
    private EntityQueryRepository entityQueryRepository;

    @Override
    public long countEntitiesByQuery(TenantId tenantId, CustomerId customerId, EntityCountQuery query) {
        return entityQueryRepository.countEntitiesByQuery(tenantId, customerId, query);
    }

    @Override
    public PageData<EntityData> findEntityDataByQuery(TenantId tenantId, CustomerId customerId, EntityDataQuery query) {
        return entityQueryRepository.findEntityDataByQuery(tenantId, customerId, query);
    }

    @Override
    public long countEntitiesByQuery(TenantId tenantId, CustomerId ownCustomerId, List<UUID> customerIds, CustomerScopeMode scopeMode, EntityCountQuery query) {
        return entityQueryRepository.countEntitiesByQuery(tenantId, ownCustomerId, customerIds, scopeMode, query);
    }

    @Override
    public PageData<EntityData> findEntityDataByQuery(TenantId tenantId, CustomerId ownCustomerId, List<UUID> customerIds, CustomerScopeMode scopeMode, EntityDataQuery query) {
        return entityQueryRepository.findEntityDataByQuery(tenantId, ownCustomerId, customerIds, scopeMode, query);
    }
}

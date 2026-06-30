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

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.stereotype.Service;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.EntityId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.relation.RelationService;
import org.thingsboard.server.service.security.model.SecurityUser;

import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

@Service
public class DefaultAccessScopeService implements AccessScopeService {

    private final RelationService relationService;
    private final Cache<CustomerId, AccessScope> cache;

    public DefaultAccessScopeService(RelationService relationService) {
        this.relationService = relationService;
        this.cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .build();
    }

    @Override
    public AccessScope resolve(SecurityUser user) {
        if (user.getAuthority() != Authority.CUSTOMER_USER) {
            return AccessScope.unrestricted();
        }
        CustomerId customerId = user.getCustomerId();
        PortfolioAccess.Role role = PortfolioAccess.roleOf(user);
        return cache.get(customerId, cid -> computeScope(user.getTenantId(), cid, role));
    }

    private AccessScope computeScope(TenantId tenantId, CustomerId customerId, PortfolioAccess.Role role) {
        switch (role) {
            case STAFF:
                return AccessScope.exclude(targets(tenantId, customerId, PortfolioAccess.EXCLUDED));
            case PARTY:
                return AccessScope.include(targets(tenantId, customerId, PortfolioAccess.CAN_VIEW));
            case ADMIN_OPS:
            case LEGACY:
            default:
                return AccessScope.include(Set.of(customerId));
        }
    }

    private Set<CustomerId> targets(TenantId tenantId, CustomerId customerId, String relationType) {
        List<EntityRelation> relations =
                relationService.findByFromAndType(tenantId, customerId, relationType, PortfolioAccess.RELATION_GROUP);
        Set<CustomerId> result = new HashSet<>();
        for (EntityRelation relation : relations) {
            EntityId to = relation.getTo();
            if (to != null && to.getEntityType() == EntityType.CUSTOMER) {
                result.add(new CustomerId(to.getId()));
            }
        }
        return result;
    }

    @Override
    public boolean canView(SecurityUser user, CustomerId entityCustomerId) {
        return resolve(user).canView(entityCustomerId);
    }

    @Override
    public void invalidate(CustomerId customerId) {
        cache.invalidate(customerId);
    }

    @Override
    public void invalidateAll() {
        cache.invalidateAll();
    }
}

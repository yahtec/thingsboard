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

import com.fasterxml.jackson.databind.JsonNode;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.stereotype.Service;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.UserAuthDetails;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.EntityId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.relation.RelationService;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.user.cache.UserAuthDetailsCache;

import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

@Service
public class DefaultAccessScopeService implements AccessScopeService {

    private final RelationService relationService;
    private final UserAuthDetailsCache userAuthDetailsCache;
    private final Cache<ScopeCacheKey, AccessScope> cache;

    /**
     * Cache key composite (customerId + role). Deux users du MEME customer mais de roles
     * differents (ex. PARTY vs STAFF) ne doivent PAS partager la meme entree de cache, sinon le
     * premier resolu impose son scope au second.
     */
    private record ScopeCacheKey(CustomerId customerId, PortfolioAccess.Role role) {
    }

    public DefaultAccessScopeService(RelationService relationService, UserAuthDetailsCache userAuthDetailsCache) {
        this.relationService = relationService;
        this.userAuthDetailsCache = userAuthDetailsCache;
        this.cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .build();
    }

    /**
     * Returns the portfolio role for a user, falling back to a DB lookup if
     * additionalInfo is absent from the JWT-parsed SecurityUser.
     */
    private PortfolioAccess.Role resolveRole(SecurityUser user) {
        JsonNode info = user.getAdditionalInfo();
        if (info != null && info.hasNonNull(PortfolioAccess.ROLE_FIELD)) {
            return PortfolioAccess.roleOf(user);
        }
        // JWT tokens do not carry additionalInfo — load the full user from cache/DB.
        UserAuthDetails details = userAuthDetailsCache.getUserAuthDetails(user.getTenantId(), user.getId());
        if (details != null) {
            return PortfolioAccess.roleOf(details.user());
        }
        return PortfolioAccess.Role.LEGACY;
    }

    @Override
    public AccessScope resolve(SecurityUser user) {
        if (user.getAuthority() != Authority.CUSTOMER_USER) {
            return AccessScope.unrestricted();
        }
        CustomerId customerId = user.getCustomerId();
        PortfolioAccess.Role role = resolveRole(user);
        return cache.get(new ScopeCacheKey(customerId, role),
                key -> computeScope(user.getTenantId(), key.customerId(), key.role()));
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
    public boolean isReadOnly(SecurityUser user) {
        if (user.getAuthority() != Authority.CUSTOMER_USER) {
            return false;
        }
        PortfolioAccess.Role role = resolveRole(user);
        return role == PortfolioAccess.Role.PARTY || role == PortfolioAccess.Role.STAFF;
    }

    @Override
    public void invalidate(CustomerId customerId) {
        if (customerId == null) {
            return;
        }
        // La cle est composite (customerId, role) : on purge toutes les entrees de ce customer,
        // quel que soit le role.
        cache.asMap().keySet().removeIf(key -> customerId.equals(key.customerId()));
    }

    @Override
    public void invalidateAll() {
        cache.invalidateAll();
    }
}

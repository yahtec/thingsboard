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
package org.thingsboard.server.service.subscription;

import lombok.extern.slf4j.Slf4j;
import org.thingsboard.server.common.data.permission.CustomerScopeMode;
import org.thingsboard.server.common.data.query.EntityCountQuery;
import org.thingsboard.server.dao.attributes.AttributesService;
import org.thingsboard.server.dao.entity.EntityService;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.security.scope.AccessScope;
import org.thingsboard.server.service.security.scope.AccessScopeService;
import org.thingsboard.server.service.ws.WebSocketService;
import org.thingsboard.server.service.ws.WebSocketSessionRef;
import org.thingsboard.server.service.ws.telemetry.cmd.v2.EntityCountUpdate;

@Slf4j
public class TbEntityCountSubCtx extends TbAbstractEntityQuerySubCtx<EntityCountQuery> {

    private volatile int result;

    private final AccessScopeService accessScopeService;

    public TbEntityCountSubCtx(String serviceId, WebSocketService wsService, EntityService entityService,
                               TbLocalSubscriptionService localSubscriptionService, AttributesService attributesService,
                               SubscriptionServiceStatistics stats, WebSocketSessionRef sessionRef, int cmdId,
                               AccessScopeService accessScopeService) {
        super(serviceId, wsService, entityService, localSubscriptionService, attributesService, stats, sessionRef, cmdId);
        this.accessScopeService = accessScopeService;
    }

    private long countScoped() {
        SecurityUser user = sessionRef.getSecurityCtx();
        AccessScope scope = accessScopeService.resolve(user);
        if (scope.getMode() == AccessScope.Mode.UNRESTRICTED) {
            return entityService.countEntitiesByQuery(getTenantId(), getCustomerId(), query);
        }
        CustomerScopeMode mode = scope.getMode() == AccessScope.Mode.INCLUDE
                ? CustomerScopeMode.INCLUDE : CustomerScopeMode.EXCLUDE;
        return entityService.countEntitiesByQueryScoped(getTenantId(), getCustomerId(), scope.customerUuids(), mode, query);
    }

    @Override
    public void fetchData() {
        result = (int) countScoped();
        sendWsMsg(new EntityCountUpdate(cmdId, result));
    }

    @Override
    protected void update() {
        int newCount = (int) countScoped();
        if (newCount != result) {
            result = newCount;
            sendWsMsg(new EntityCountUpdate(cmdId, result));
        }
    }

    @Override
    public boolean isDynamic() {
        return true;
    }
}

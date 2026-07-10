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
package org.thingsboard.server.service.security.permission;

import org.springframework.stereotype.Component;
import org.thingsboard.server.common.data.DashboardInfo;
import org.thingsboard.server.common.data.HasCustomerId;
import org.thingsboard.server.common.data.HasTenantId;
import org.thingsboard.server.common.data.TbResourceInfo;
import org.thingsboard.server.common.data.User;
import org.thingsboard.server.common.data.id.ApiKeyId;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.DashboardId;
import org.thingsboard.server.common.data.id.EntityId;
import org.thingsboard.server.common.data.id.TbResourceId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.pat.ApiKeyInfo;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.security.scope.AccessScopeService;
import java.util.Set;

@Component
public class CustomerUserPermissions extends AbstractPermissions {

    private static final Set<Operation> READ_OPS =
            Set.of(Operation.READ, Operation.READ_ATTRIBUTES, Operation.READ_TELEMETRY);

    private final AccessScopeService accessScopeService;

    public CustomerUserPermissions(AccessScopeService accessScopeService) {
        super();
        this.accessScopeService = accessScopeService;

        put(Resource.ALARM, new PermissionChecker() {
            @Override
            public boolean hasPermission(SecurityUser user, Operation operation, EntityId entityId, HasTenantId entity) {
                if (!user.getTenantId().equals(entity.getTenantId())) {
                    return false;
                }
                if (!(entity instanceof HasCustomerId)) {
                    return false;
                }
                CustomerId entityCustomerId = ((HasCustomerId) entity).getCustomerId();
                if (accessScopeService.isReadOnly(user)) {
                    return READ_OPS.contains(operation) && accessScopeService.canView(user, entityCustomerId);
                }
                return accessScopeService.canView(user, entityCustomerId);
            }
        });

        put(Resource.ASSET, customerEntityPermissionChecker());
        put(Resource.DEVICE, customerEntityPermissionChecker());
        put(Resource.CUSTOMER, customerPermissionChecker());
        put(Resource.DASHBOARD, customerDashboardPermissionChecker);
        put(Resource.ENTITY_VIEW, customerEntityPermissionChecker());
        put(Resource.USER, userPermissionChecker);
        put(Resource.WIDGETS_BUNDLE, widgetsPermissionChecker);
        put(Resource.WIDGET_TYPE, widgetsPermissionChecker);
        put(Resource.EDGE, customerEntityPermissionChecker());
        put(Resource.RPC, rpcPermissionChecker);
        put(Resource.DEVICE_PROFILE, profilePermissionChecker);
        put(Resource.ASSET_PROFILE, profilePermissionChecker);
        put(Resource.TB_RESOURCE, customerResourcePermissionChecker);
        put(Resource.MOBILE_APP_SETTINGS, new PermissionChecker.GenericPermissionChecker(Operation.READ));
        put(Resource.API_KEY, apiKeysPermissionChecker);
    }

    private PermissionChecker customerEntityPermissionChecker() {
        return new PermissionChecker.GenericPermissionChecker(Operation.READ, Operation.READ_CREDENTIALS,
                Operation.READ_ATTRIBUTES, Operation.READ_TELEMETRY, Operation.RPC_CALL, Operation.CLAIM_DEVICES,
                Operation.WRITE, Operation.WRITE_ATTRIBUTES, Operation.WRITE_TELEMETRY) {

            @Override
            @SuppressWarnings("unchecked")
            public boolean hasPermission(SecurityUser user, Operation operation, EntityId entityId, HasTenantId entity) {
                if (!super.hasPermission(user, operation, entityId, entity)) {
                    return false;
                }
                if (!user.getTenantId().equals(entity.getTenantId())) {
                    return false;
                }
                if (!(entity instanceof HasCustomerId)) {
                    return false;
                }
                CustomerId entityCustomerId = ((HasCustomerId) entity).getCustomerId();
                if (accessScopeService.isReadOnly(user)) {
                    return READ_OPS.contains(operation) && accessScopeService.canView(user, entityCustomerId);
                }
                return operation.equals(Operation.CLAIM_DEVICES) || accessScopeService.canView(user, entityCustomerId);
            }
        };
    }

    /**
     * Checker de la ressource CUSTOMER. En lecture seule (READ/READ_ATTRIBUTES/READ_TELEMETRY),
     * autorise :
     *  - son PROPRE customer (comportement legacy, toujours vrai indépendamment du scope) ;
     *  - tout customer de site que l'utilisateur peut voir via le scope portefeuille
     *    ({@code accessScopeService.canView}) — un PARTY a besoin de lire l'entité customer de ses
     *    sites (titre, adresse) pour les widgets.
     * Aucune opération d'écriture n'est enregistrée → l'écriture reste refusée (own-customer only via
     * les autres chemins). {@code canView} sur son propre customer reste vrai pour les rôles legacy.
     */
    private PermissionChecker customerPermissionChecker() {
        return new PermissionChecker.GenericPermissionChecker(Operation.READ, Operation.READ_ATTRIBUTES, Operation.READ_TELEMETRY) {

            @Override
            @SuppressWarnings("unchecked")
            public boolean hasPermission(SecurityUser user, Operation operation, EntityId entityId, HasTenantId entity) {
                if (!super.hasPermission(user, operation, entityId, entity)) {
                    return false;
                }
                if (user.getCustomerId().equals(entityId)) {
                    return true;
                }
                return accessScopeService.canView(user, new CustomerId(entityId.getId()));
            }

        };
    }

    private static final PermissionChecker customerResourcePermissionChecker =
            new PermissionChecker<TbResourceId, TbResourceInfo>() {

                @Override
                @SuppressWarnings("unchecked")
                public boolean hasPermission(SecurityUser user, Operation operation, TbResourceId resourceId, TbResourceInfo resource) {
                    if (operation != Operation.READ) {
                        return false;
                    }
                    if (resource.getResourceType() == null || !resource.getResourceType().isCustomerAccess()) {
                        return false;
                    }
                    if (resource.getTenantId() == null || resource.getTenantId().isNullUid()) {
                        return true;
                    }
                    return user.getTenantId().equals(resource.getTenantId());
                }

            };

    private static final PermissionChecker customerDashboardPermissionChecker =
            new PermissionChecker.GenericPermissionChecker<DashboardId, DashboardInfo>(Operation.READ, Operation.READ_ATTRIBUTES, Operation.READ_TELEMETRY) {

                @Override
                public boolean hasPermission(SecurityUser user, Operation operation, DashboardId dashboardId, DashboardInfo dashboard) {

                    if (!super.hasPermission(user, operation, dashboardId, dashboard)) {
                        return false;
                    }
                    if (!user.getTenantId().equals(dashboard.getTenantId())) {
                        return false;
                    }
                    return dashboard.isAssignedToCustomer(user.getCustomerId());
                }

            };

    private static final PermissionChecker userPermissionChecker = new PermissionChecker<UserId, User>() {

        @Override
        public boolean hasPermission(SecurityUser user, Operation operation, UserId userId, User userEntity) {
            if (!Authority.CUSTOMER_USER.equals(userEntity.getAuthority())) {
                return false;
            }

            if (!user.getCustomerId().equals(userEntity.getCustomerId())) {
                return false;
            }

            if (Operation.READ.equals(operation)) {
                return true;
            }

            return user.getId().equals(userId);
        }

    };

    private static final PermissionChecker widgetsPermissionChecker = new PermissionChecker.GenericPermissionChecker(Operation.READ) {

        @Override
        @SuppressWarnings("unchecked")
        public boolean hasPermission(SecurityUser user, Operation operation, EntityId entityId, HasTenantId entity) {
            if (!super.hasPermission(user, operation, entityId, entity)) {
                return false;
            }
            if (entity.getTenantId() == null || entity.getTenantId().isNullUid()) {
                return true;
            }
            return user.getTenantId().equals(entity.getTenantId());
        }

    };

    private static final PermissionChecker rpcPermissionChecker = new PermissionChecker.GenericPermissionChecker(Operation.READ) {

        @Override
        @SuppressWarnings("unchecked")
        public boolean hasPermission(SecurityUser user, Operation operation, EntityId entityId, HasTenantId entity) {
            if (!super.hasPermission(user, operation, entityId, entity)) {
                return false;
            }
            if (entity.getTenantId() == null || entity.getTenantId().isNullUid()) {
                return true;
            }
            return user.getTenantId().equals(entity.getTenantId());
        }
    };

    private static final PermissionChecker profilePermissionChecker = new PermissionChecker.GenericPermissionChecker(Operation.READ) {

        @Override
        @SuppressWarnings("unchecked")
        public boolean hasPermission(SecurityUser user, Operation operation, EntityId entityId, HasTenantId entity) {
            if (!super.hasPermission(user, operation, entityId, entity)) {
                return false;
            }
            if (entity.getTenantId() == null || entity.getTenantId().isNullUid()) {
                return true;
            }
            return user.getTenantId().equals(entity.getTenantId());
        }
    };

    private static final PermissionChecker apiKeysPermissionChecker = new PermissionChecker<ApiKeyId, ApiKeyInfo>() {

        @Override
        public boolean hasPermission(SecurityUser user, Operation operation) {
            return true;
        }

        @Override
        @SuppressWarnings("unchecked")
        public boolean hasPermission(SecurityUser user, Operation operation, ApiKeyId entityId, ApiKeyInfo entity) {
            return user.getTenantId().equals(entity.getTenantId());
        }
    };

}

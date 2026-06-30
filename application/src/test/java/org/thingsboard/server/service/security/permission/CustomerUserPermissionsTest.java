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

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.thingsboard.server.common.data.Device;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.DeviceId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.security.scope.AccessScopeService;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CustomerUserPermissionsTest {

    @Mock
    AccessScopeService accessScopeService;

    CustomerUserPermissions permissions;

    final TenantId tenantId = new TenantId(UUID.randomUUID());

    @BeforeEach
    void setUp() {
        permissions = new CustomerUserPermissions(accessScopeService);
    }

    private SecurityUser customerUser(CustomerId customerId) {
        SecurityUser u = new SecurityUser(new UserId(UUID.randomUUID()));
        u.setAuthority(Authority.CUSTOMER_USER);
        u.setTenantId(tenantId);
        u.setCustomerId(customerId);
        return u;
    }

    private Device device(CustomerId owner) {
        Device d = new Device(new DeviceId(UUID.randomUUID()));
        d.setTenantId(tenantId);
        d.setCustomerId(owner);
        return d;
    }

    private PermissionChecker deviceChecker() {
        Optional<PermissionChecker> c = permissions.getPermissionChecker(Resource.DEVICE);
        assertThat(c).isPresent();
        return c.get();
    }

    @Test
    @SuppressWarnings("unchecked")
    void scopedReadAllowedWhenInScope() {
        SecurityUser user = customerUser(new CustomerId(UUID.randomUUID()));
        CustomerId site = new CustomerId(UUID.randomUUID());
        Device d = device(site);
        when(accessScopeService.isReadOnly(user)).thenReturn(true);
        when(accessScopeService.canView(user, site)).thenReturn(true);

        assertThat(deviceChecker().hasPermission(user, Operation.READ, d.getId(), d)).isTrue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void scopedReadDeniedWhenOutOfScope() {
        SecurityUser user = customerUser(new CustomerId(UUID.randomUUID()));
        CustomerId site = new CustomerId(UUID.randomUUID());
        Device d = device(site);
        when(accessScopeService.isReadOnly(user)).thenReturn(true);
        when(accessScopeService.canView(user, site)).thenReturn(false);

        assertThat(deviceChecker().hasPermission(user, Operation.READ, d.getId(), d)).isFalse();
    }

    @Test
    @SuppressWarnings("unchecked")
    void scopedWriteAlwaysDenied() {
        SecurityUser user = customerUser(new CustomerId(UUID.randomUUID()));
        CustomerId site = new CustomerId(UUID.randomUUID());
        Device d = device(site);
        when(accessScopeService.isReadOnly(user)).thenReturn(true);
        lenient().when(accessScopeService.canView(user, site)).thenReturn(true);

        assertThat(deviceChecker().hasPermission(user, Operation.WRITE, d.getId(), d)).isFalse();
        assertThat(deviceChecker().hasPermission(user, Operation.READ_CREDENTIALS, d.getId(), d)).isFalse();
    }

    @Test
    @SuppressWarnings("unchecked")
    void legacyUserBehavesLikeEquality() {
        CustomerId own = new CustomerId(UUID.randomUUID());
        SecurityUser user = customerUser(own);
        Device mine = device(own);
        when(accessScopeService.isReadOnly(user)).thenReturn(false);
        when(accessScopeService.canView(user, own)).thenReturn(true);

        // legacy garde l'écriture sur ses propres entités
        assertThat(deviceChecker().hasPermission(user, Operation.WRITE, mine.getId(), mine)).isTrue();
    }
}

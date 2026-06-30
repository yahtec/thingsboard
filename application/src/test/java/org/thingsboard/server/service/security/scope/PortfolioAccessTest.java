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

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.thingsboard.common.util.JacksonUtil;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.service.security.model.SecurityUser;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class PortfolioAccessTest {

    private SecurityUser userWithRole(String role) {
        SecurityUser u = new SecurityUser(new UserId(UUID.randomUUID()));
        if (role != null) {
            ObjectNode info = JacksonUtil.newObjectNode();
            info.put(PortfolioAccess.ROLE_FIELD, role);
            u.setAdditionalInfo(info);
        }
        return u;
    }

    @Test
    void parsesPartyRole() {
        assertThat(PortfolioAccess.roleOf(userWithRole("PARTY"))).isEqualTo(PortfolioAccess.Role.PARTY);
    }

    @Test
    void parsesStaffCaseInsensitive() {
        assertThat(PortfolioAccess.roleOf(userWithRole("staff"))).isEqualTo(PortfolioAccess.Role.STAFF);
    }

    @Test
    void missingRoleIsLegacy() {
        assertThat(PortfolioAccess.roleOf(userWithRole(null))).isEqualTo(PortfolioAccess.Role.LEGACY);
    }

    @Test
    void unknownRoleIsLegacy() {
        assertThat(PortfolioAccess.roleOf(userWithRole("bogus"))).isEqualTo(PortfolioAccess.Role.LEGACY);
    }
}

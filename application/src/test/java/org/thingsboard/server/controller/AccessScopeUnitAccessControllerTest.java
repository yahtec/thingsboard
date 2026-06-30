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
package org.thingsboard.server.controller;

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.thingsboard.common.util.JacksonUtil;
import org.thingsboard.server.common.data.Customer;
import org.thingsboard.server.common.data.Device;
import org.thingsboard.server.common.data.User;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.DeviceId;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.common.data.relation.RelationTypeGroup;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.service.DaoSqlTest;
import org.thingsboard.server.service.security.scope.PortfolioAccess;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@DaoSqlTest
public class AccessScopeUnitAccessControllerTest extends AbstractControllerTest {

    private static final String PARTY_USER_EMAIL = "party-user@test.thingsboard.org";
    private static final String PARTY_USER_PASSWORD = "party1234";

    private CustomerId siteAId;
    private CustomerId siteBId;
    private CustomerId partyCustomerId;

    private DeviceId deviceAId;
    private DeviceId deviceBId;

    private User partyUser;

    @Before
    public void setup() throws Exception {
        loginTenantAdmin();

        // 1. Create siteA and siteB customers
        Customer siteA = new Customer();
        siteA.setTitle("SiteA");
        siteA.setTenantId(tenantId);
        Customer savedSiteA = doPost("/api/customer", siteA, Customer.class);
        siteAId = savedSiteA.getId();

        Customer siteB = new Customer();
        siteB.setTitle("SiteB");
        siteB.setTenantId(tenantId);
        Customer savedSiteB = doPost("/api/customer", siteB, Customer.class);
        siteBId = savedSiteB.getId();

        // 2. Create deviceA and deviceB, assign to respective sites
        Device deviceA = new Device();
        deviceA.setName("DeviceA");
        deviceA.setType("default");
        deviceA.setTenantId(tenantId);
        Device savedDeviceA = doPost("/api/device", deviceA, Device.class);
        deviceAId = savedDeviceA.getId();
        assignDeviceToCustomer(deviceAId, siteAId);

        Device deviceB = new Device();
        deviceB.setName("DeviceB");
        deviceB.setType("default");
        deviceB.setTenantId(tenantId);
        Device savedDeviceB = doPost("/api/device", deviceB, Device.class);
        deviceBId = savedDeviceB.getId();
        assignDeviceToCustomer(deviceBId, siteBId);

        // 3. Create partyCustomer and partyUser with portfolioRole=PARTY
        Customer partyCustomer = new Customer();
        partyCustomer.setTitle("PartyCustomer");
        partyCustomer.setTenantId(tenantId);
        Customer savedPartyCustomer = doPost("/api/customer", partyCustomer, Customer.class);
        partyCustomerId = savedPartyCustomer.getId();

        User partyUserSpec = new User();
        partyUserSpec.setAuthority(Authority.CUSTOMER_USER);
        partyUserSpec.setTenantId(tenantId);
        partyUserSpec.setCustomerId(partyCustomerId);
        partyUserSpec.setEmail(PARTY_USER_EMAIL);
        ObjectNode additionalInfo = JacksonUtil.newObjectNode();
        additionalInfo.put(PortfolioAccess.ROLE_FIELD, "PARTY");
        partyUserSpec.setAdditionalInfo(additionalInfo);
        partyUser = createUserAndActivate(partyUserSpec, PARTY_USER_PASSWORD);

        // 4. Create CanView relation: partyCustomer -> siteA
        EntityRelation canViewRelation = new EntityRelation(partyCustomerId, siteAId,
                PortfolioAccess.CAN_VIEW, RelationTypeGroup.COMMON);
        doPost("/api/relation", canViewRelation).andExpect(status().isOk());

        resetTokens();
    }

    @After
    public void teardown() throws Exception {
        // AbstractWebTest.teardownWebTest() handles tenant cleanup
    }

    @Test
    public void partyUserCanReadDeviceInScope() throws Exception {
        loginUser(PARTY_USER_EMAIL, PARTY_USER_PASSWORD);

        doGet("/api/device/" + deviceAId.getId().toString(), Device.class);
    }

    @Test
    public void partyUserCannotReadDeviceOutOfScope() throws Exception {
        loginUser(PARTY_USER_EMAIL, PARTY_USER_PASSWORD);

        doGet("/api/device/" + deviceBId.getId().toString())
                .andExpect(status().isForbidden())
                .andExpect(statusReason(containsString(msgErrorPermission)));
    }

    @Test
    public void partyUserCannotWriteDeviceInScope() throws Exception {
        loginTenantAdmin();
        Device deviceA = doGet("/api/device/" + deviceAId.getId().toString(), Device.class);

        loginUser(PARTY_USER_EMAIL, PARTY_USER_PASSWORD);

        deviceA.setName("DeviceA-Modified");
        doPost("/api/device", deviceA)
                .andExpect(status().isForbidden())
                .andExpect(statusReason(containsString(msgErrorPermission)));
    }

    @Test
    public void legacyCustomerUserCanReadOwnDevice() throws Exception {
        // The default customerUser created by AbstractWebTest has customerId = customerId
        // Create a device for that customer
        loginTenantAdmin();
        Device legacyDevice = new Device();
        legacyDevice.setName("LegacyDevice");
        legacyDevice.setType("default");
        legacyDevice.setTenantId(tenantId);
        Device savedLegacyDevice = doPost("/api/device", legacyDevice, Device.class);
        assignDeviceToCustomer(savedLegacyDevice.getId(), customerId);

        loginCustomerUser();

        doGet("/api/device/" + savedLegacyDevice.getId().getId().toString(), Device.class);
    }

    @Test
    public void legacyCustomerUserCannotReadDeviceOutOfScope() throws Exception {
        loginCustomerUser();

        doGet("/api/device/" + deviceAId.getId().toString())
                .andExpect(status().isForbidden())
                .andExpect(statusReason(containsString(msgErrorPermission)));
    }
}

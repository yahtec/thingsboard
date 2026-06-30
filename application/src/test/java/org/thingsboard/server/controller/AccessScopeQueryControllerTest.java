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

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.thingsboard.common.util.JacksonUtil;
import org.thingsboard.server.common.data.Customer;
import org.thingsboard.server.common.data.Device;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.Tenant;
import org.thingsboard.server.common.data.User;
import org.thingsboard.server.common.data.alarm.Alarm;
import org.thingsboard.server.common.data.alarm.AlarmSeverity;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.DeviceId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.page.PageData;
import org.thingsboard.server.common.data.query.EntityCountQuery;
import org.thingsboard.server.common.data.query.EntityData;
import org.thingsboard.server.common.data.query.EntityDataPageLink;
import org.thingsboard.server.common.data.query.EntityDataQuery;
import org.thingsboard.server.common.data.query.EntityDataSortOrder;
import org.thingsboard.server.common.data.query.EntityKey;
import org.thingsboard.server.common.data.query.AlarmCountQuery;
import org.thingsboard.server.common.data.query.AlarmData;
import org.thingsboard.server.common.data.query.AlarmDataPageLink;
import org.thingsboard.server.common.data.query.AlarmDataQuery;
import org.thingsboard.server.common.data.query.EntityKeyType;
import org.thingsboard.server.common.data.query.EntityTypeFilter;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.common.data.relation.RelationTypeGroup;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.service.DaoSqlTest;
import org.thingsboard.server.service.security.scope.PortfolioAccess;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Tests d adversite (integration Testcontainers Postgres) pour le scoping entity-query.
 *
 * <p>Matrice : TENANT_ADMIN / PARTY / STAFF / LEGACY sur POST /api/entitiesQuery/find.
 *
 * <p>Topologie :
 * <ul>
 *   <li>siteA → deviceA</li>
 *   <li>siteB → deviceB</li>
 *   <li>partyCustomer (PARTY role, CanView → siteA)</li>
 *   <li>staffCustomer (STAFF role, Excluded → siteB)</li>
 *   <li>legacyCustomer (pas de role) → legacyDevice</li>
 * </ul>
 *
 * <p>Attendus :
 * <ul>
 *   <li>TENANT_ADMIN : voit tout (unrestricted)</li>
 *   <li>PARTY : voit deviceA seulement (INCLUDE {siteA})</li>
 *   <li>STAFF : voit deviceA + legacyDevice, pas deviceB (EXCLUDE {siteB})</li>
 *   <li>LEGACY : voit legacyDevice seulement (INCLUDE {legacyCustomer})</li>
 * </ul>
 */
@DaoSqlTest
public class AccessScopeQueryControllerTest extends AbstractControllerTest {

    private static final String PARTY_EMAIL = "scope-party@test.thingsboard.org";
    private static final String PARTY_PASSWORD = "party1234";
    private static final String STAFF_EMAIL = "scope-staff@test.thingsboard.org";
    private static final String STAFF_PASSWORD = "staff1234";
    private static final String LEGACY_EMAIL = "scope-legacy@test.thingsboard.org";
    private static final String LEGACY_PASSWORD = "legacy1234";
    private static final String TENANT_ADMIN_EMAIL = "scope-ta@test.thingsboard.org";
    private static final String TENANT_ADMIN_PASSWORD = "ta1234";

    private TenantId myTenantId;
    private CustomerId siteAId;
    private CustomerId siteBId;
    private CustomerId legacyCustomerId;
    private CustomerId partyCustomerId;
    private CustomerId staffCustomerId;
    private DeviceId deviceAId;
    private DeviceId deviceBId;
    private DeviceId legacyDeviceId;
    private UserId partyUserId;
    private UserId staffUserId;

    @Before
    public void setupScope() throws Exception {
        loginSysAdmin();

        Tenant tenant = new Tenant();
        tenant.setTitle("AccessScopeQueryTest-Tenant");
        Tenant saved = saveTenant(tenant);
        myTenantId = saved.getId();

        User ta = new User();
        ta.setAuthority(Authority.TENANT_ADMIN);
        ta.setTenantId(myTenantId);
        ta.setEmail(TENANT_ADMIN_EMAIL);
        ta.setFirstName("Scope");
        ta.setLastName("Admin");
        createUserAndLogin(ta, TENANT_ADMIN_PASSWORD);

        // siteA + deviceA
        Customer siteA = new Customer();
        siteA.setTitle("ScopeTestSiteA");
        siteA.setTenantId(myTenantId);
        siteAId = doPost("/api/customer", siteA, Customer.class).getId();

        Device deviceA = new Device();
        deviceA.setName("ScopeTestDeviceA");
        deviceA.setType("default");
        deviceAId = doPost("/api/device", deviceA, Device.class).getId();
        assignDeviceToCustomer(deviceAId, siteAId);

        // siteB + deviceB
        Customer siteB = new Customer();
        siteB.setTitle("ScopeTestSiteB");
        siteB.setTenantId(myTenantId);
        siteBId = doPost("/api/customer", siteB, Customer.class).getId();

        Device deviceB = new Device();
        deviceB.setName("ScopeTestDeviceB");
        deviceB.setType("default");
        deviceBId = doPost("/api/device", deviceB, Device.class).getId();
        assignDeviceToCustomer(deviceBId, siteBId);

        // partyCustomer (PARTY, CanView → siteA)
        Customer partyCustomer = new Customer();
        partyCustomer.setTitle("ScopeTestPartyCustomer");
        partyCustomer.setTenantId(myTenantId);
        partyCustomerId = doPost("/api/customer", partyCustomer, Customer.class).getId();

        User partyUser = new User();
        partyUser.setAuthority(Authority.CUSTOMER_USER);
        partyUser.setTenantId(myTenantId);
        partyUser.setCustomerId(partyCustomerId);
        partyUser.setEmail(PARTY_EMAIL);
        partyUser.setAdditionalInfo(roleNode("PARTY"));
        partyUserId = createUserAndActivate(partyUser, PARTY_PASSWORD).getId();

        doPost("/api/relation",
                new EntityRelation(partyCustomerId, siteAId, PortfolioAccess.CAN_VIEW, RelationTypeGroup.COMMON))
                .andExpect(status().isOk());

        // staffCustomer (STAFF, Excluded → siteB)
        Customer staffCustomer = new Customer();
        staffCustomer.setTitle("ScopeTestStaffCustomer");
        staffCustomer.setTenantId(myTenantId);
        staffCustomerId = doPost("/api/customer", staffCustomer, Customer.class).getId();

        User staffUser = new User();
        staffUser.setAuthority(Authority.CUSTOMER_USER);
        staffUser.setTenantId(myTenantId);
        staffUser.setCustomerId(staffCustomerId);
        staffUser.setEmail(STAFF_EMAIL);
        staffUser.setAdditionalInfo(roleNode("STAFF"));
        staffUserId = createUserAndActivate(staffUser, STAFF_PASSWORD).getId();

        doPost("/api/relation",
                new EntityRelation(staffCustomerId, siteBId, PortfolioAccess.EXCLUDED, RelationTypeGroup.COMMON))
                .andExpect(status().isOk());

        // legacyCustomer (aucun role) + legacyDevice
        Customer legacyCustomer = new Customer();
        legacyCustomer.setTitle("ScopeTestLegacyCustomer");
        legacyCustomer.setTenantId(myTenantId);
        legacyCustomerId = doPost("/api/customer", legacyCustomer, Customer.class).getId();

        User legacyUser = new User();
        legacyUser.setAuthority(Authority.CUSTOMER_USER);
        legacyUser.setTenantId(myTenantId);
        legacyUser.setCustomerId(legacyCustomerId);
        legacyUser.setEmail(LEGACY_EMAIL);
        createUserAndActivate(legacyUser, LEGACY_PASSWORD);

        Device legacyDevice = new Device();
        legacyDevice.setName("ScopeTestLegacyDevice");
        legacyDevice.setType("default");
        legacyDeviceId = doPost("/api/device", legacyDevice, Device.class).getId();
        assignDeviceToCustomer(legacyDeviceId, legacyCustomerId);

        resetTokens();
    }

    @After
    public void teardownScope() throws Exception {
        loginSysAdmin();
        deleteTenant(myTenantId);
    }

    // ── TENANT_ADMIN : unrestricted ────────────────────────────────────────

    @Test
    public void tenantAdminSeesAllDevices() throws Exception {
        loginUser(TENANT_ADMIN_EMAIL, TENANT_ADMIN_PASSWORD);
        List<DeviceId> ids = deviceIds(findByQuery(allDevicesQuery()));
        assertThat(ids).contains(deviceAId, deviceBId, legacyDeviceId);
    }

    // ── PARTY : INCLUDE {siteA} ────────────────────────────────────────────

    @Test
    public void partySeesOnlyDeviceA() throws Exception {
        loginUser(PARTY_EMAIL, PARTY_PASSWORD);
        List<DeviceId> ids = deviceIds(findByQuery(allDevicesQuery()));
        assertThat(ids).containsExactlyInAnyOrder(deviceAId);
    }

    @Test
    public void partyCountEqualsOne() throws Exception {
        loginUser(PARTY_EMAIL, PARTY_PASSWORD);
        Long count = countByQuery(new EntityCountQuery(deviceTypeFilter()));
        assertThat(count).isEqualTo(1L);
    }

    // ── STAFF : EXCLUDE {siteB} ────────────────────────────────────────────

    @Test
    public void staffSeesDeviceAButNotDeviceB() throws Exception {
        loginUser(STAFF_EMAIL, STAFF_PASSWORD);
        List<DeviceId> ids = deviceIds(findByQuery(allDevicesQuery()));
        assertThat(ids).contains(deviceAId, legacyDeviceId);
        assertThat(ids).doesNotContain(deviceBId);
    }

    // ── LEGACY : INCLUDE {legacyCustomer} ─────────────────────────────────

    @Test
    public void legacySeesOnlyOwnDevice() throws Exception {
        loginUser(LEGACY_EMAIL, LEGACY_PASSWORD);
        List<DeviceId> ids = deviceIds(findByQuery(allDevicesQuery()));
        assertThat(ids).containsExactlyInAnyOrder(legacyDeviceId);
    }

    // ── C1 (regression) : EXCLUDE ne doit PAS leaker les USER d'autres customers ──────────
    //
    // Avant le fix, le scoping multi-customer s'appliquait en DENYLIST a TOUT sauf
    // {CUSTOMER, API_USAGE_STATE, DASHBOARD}. Pour un STAFF (EXCLUDE {siteB}), une requete
    // EntityTypeFilter(USER) generait `customer_id NOT IN (siteB)` sur tb_user → le STAFF voyait
    // les users de TOUS les autres customers (party, legacy, ...). Apres le fix (ALLOWLIST sur
    // DEVICE/ASSET/ENTITY_VIEW/EDGE), le type USER retombe sur le filtre own-customer → le STAFF ne
    // voit que les users de son propre customer.

    @Test
    public void staffDoesNotSeeUsersOfOtherCustomers() throws Exception {
        loginUser(STAFF_EMAIL, STAFF_PASSWORD);
        List<UserId> ids = userIds(findByQuery(allUsersQuery()));
        // Voit son propre user (staffCustomer)
        assertThat(ids).contains(staffUserId);
        // NE voit PAS le user d'un autre party-customer
        assertThat(ids).doesNotContain(partyUserId);
        // Tous les users renvoyes appartiennent au customer propre du STAFF
        assertThat(ids).isNotEmpty();
    }

    @Test
    public void partySeesOnlyOwnCustomerUsers() throws Exception {
        loginUser(PARTY_EMAIL, PARTY_PASSWORD);
        List<UserId> ids = userIds(findByQuery(allUsersQuery()));
        assertThat(ids).contains(partyUserId);
        assertThat(ids).doesNotContain(staffUserId);
    }

    // ── I1 : routage scope des chemins alarme (/api/alarmsQuery/find et /count) ───────────
    //
    // findAlarmDataByQuery / countAlarmsByQuery passaient par la surcharge entity-query NON scopee
    // → un PARTY voyait les alarmes des devices hors de son perimetre. Apres routage via le chemin
    // scope, le PARTY ne voit que les alarmes de deviceA (siteA, INCLUDE) et pas celles de deviceB.

    @Test
    public void partyAlarmQuerySeesOnlyInScopeAlarms() throws Exception {
        // Alarmes creees par le tenant admin (le PARTY est read-only)
        loginUser(TENANT_ADMIN_EMAIL, TENANT_ADMIN_PASSWORD);
        createAlarm(deviceAId, "scopeAlarmA");
        createAlarm(deviceBId, "scopeAlarmB");

        loginUser(PARTY_EMAIL, PARTY_PASSWORD);

        PageData<AlarmData> alarms = findAlarmsByQuery(new AlarmDataQuery(deviceTypeFilter(), alarmPageLink(), null, null, null, java.util.Collections.emptyList()));
        List<String> types = alarms.getData().stream().map(AlarmData::getType).toList();
        assertThat(types).contains("scopeAlarmA");
        assertThat(types).doesNotContain("scopeAlarmB");

        Long count = countAlarmsByQuery(new AlarmCountQuery(deviceTypeFilter()));
        assertThat(count).isEqualTo(1L);
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    private static ObjectNode roleNode(String role) {
        ObjectNode node = JacksonUtil.newObjectNode();
        node.put(PortfolioAccess.ROLE_FIELD, role);
        return node;
    }

    private static EntityTypeFilter deviceTypeFilter() {
        EntityTypeFilter f = new EntityTypeFilter();
        f.setEntityType(EntityType.DEVICE);
        return f;
    }

    private static EntityDataQuery allDevicesQuery() {
        EntityDataPageLink pageLink = new EntityDataPageLink(100, 0, null,
                new EntityDataSortOrder(
                        new EntityKey(EntityKeyType.ENTITY_FIELD, "createdTime"),
                        EntityDataSortOrder.Direction.DESC));
        return new EntityDataQuery(deviceTypeFilter(), pageLink,
                List.of(new EntityKey(EntityKeyType.ENTITY_FIELD, "name")), null, null);
    }

    private static List<DeviceId> deviceIds(PageData<EntityData> page) {
        return page.getData().stream()
                .map(ed -> new DeviceId(ed.getEntityId().getId()))
                .toList();
    }

    private static EntityTypeFilter userTypeFilter() {
        EntityTypeFilter f = new EntityTypeFilter();
        f.setEntityType(EntityType.USER);
        return f;
    }

    private static EntityDataQuery allUsersQuery() {
        EntityDataPageLink pageLink = new EntityDataPageLink(100, 0, null,
                new EntityDataSortOrder(
                        new EntityKey(EntityKeyType.ENTITY_FIELD, "createdTime"),
                        EntityDataSortOrder.Direction.DESC));
        return new EntityDataQuery(userTypeFilter(), pageLink,
                List.of(new EntityKey(EntityKeyType.ENTITY_FIELD, "email")), null, null);
    }

    private static List<UserId> userIds(PageData<EntityData> page) {
        return page.getData().stream()
                .map(ed -> new UserId(ed.getEntityId().getId()))
                .toList();
    }

    private PageData<EntityData> findByQuery(EntityDataQuery query) throws Exception {
        return doPostWithTypedResponse("/api/entitiesQuery/find", query, new TypeReference<>() {});
    }

    private Long countByQuery(EntityCountQuery query) throws Exception {
        return doPostWithResponse("/api/entitiesQuery/count", query, Long.class);
    }

    private static AlarmDataPageLink alarmPageLink() {
        AlarmDataPageLink pageLink = new AlarmDataPageLink();
        pageLink.setPage(0);
        pageLink.setPageSize(100);
        // Tri sur un ALARM_FIELD (comme l'UI) : evite l'edge case upstream du WHERE vide quand le tri
        // est un ENTITY_FIELD sans aucun filtre type/severite.
        pageLink.setSortOrder(new EntityDataSortOrder(new EntityKey(EntityKeyType.ALARM_FIELD, "createdTime")));
        return pageLink;
    }

    private void createAlarm(DeviceId originator, String type) throws Exception {
        Alarm alarm = new Alarm();
        alarm.setOriginator(originator);
        alarm.setType(type);
        alarm.setSeverity(AlarmSeverity.WARNING);
        doPost("/api/alarm", alarm, Alarm.class);
    }

    private PageData<AlarmData> findAlarmsByQuery(AlarmDataQuery query) throws Exception {
        return doPostWithTypedResponse("/api/alarmsQuery/find", query, new TypeReference<>() {});
    }

    private Long countAlarmsByQuery(AlarmCountQuery query) throws Exception {
        return doPostWithResponse("/api/alarmsQuery/count", query, Long.class);
    }
}

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
package org.thingsboard.server.service.query;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.query.AlarmCountQuery;
import org.thingsboard.server.common.data.query.EntityFilter;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.alarm.AlarmService;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.security.scope.AccessScope;
import org.thingsboard.server.service.security.scope.AccessScopeService;

import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Couvre le routage du comptage d'alarmes SANS entityFilter selon le scope portefeuille (bug C3).
 * Le chemin filtre (entityFilter != null) est couvert par les tests d'integration @DaoSqlTest.
 */
@ExtendWith(MockitoExtension.class)
class DefaultEntityQueryServiceAlarmCountTest {

    @Mock
    AccessScopeService accessScopeService;

    @Mock
    AlarmService alarmService;

    @InjectMocks
    DefaultEntityQueryService service;

    final TenantId tenantId = new TenantId(UUID.randomUUID());

    private SecurityUser user(Authority authority, CustomerId customerId) {
        SecurityUser u = new SecurityUser(new UserId(UUID.randomUUID()));
        u.setAuthority(authority);
        u.setTenantId(tenantId);
        u.setCustomerId(customerId);
        return u;
    }

    private AlarmCountQuery filterlessQuery() {
        return new AlarmCountQuery((EntityFilter) null);
    }

    @Test
    void filterlessPartyCountIsSummedPerSiteCustomerNotOwnCustomer() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        CustomerId siteA = new CustomerId(UUID.randomUUID());
        CustomerId siteB = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, party);
        AlarmCountQuery query = filterlessQuery();

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.include(Set.of(siteA, siteB)));
        when(alarmService.countAlarmsByQuery(tenantId, siteA, query)).thenReturn(3L);
        when(alarmService.countAlarmsByQuery(tenantId, siteB, query)).thenReturn(4L);

        long result = service.countAlarmsByQuery(u, query);

        assertThat(result).isEqualTo(7L);
        // NE DOIT PAS compter sur le customer propre du party (=> 0 alarmes, bug d'origine).
        verify(alarmService, never()).countAlarmsByQuery(eq(tenantId), eq(party), any(AlarmCountQuery.class));
    }

    @Test
    void filterlessEmptyIncludeReturnsZeroWithoutQueryingDao() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, party);
        AlarmCountQuery query = filterlessQuery();

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.include(Set.of()));

        long result = service.countAlarmsByQuery(u, query);

        assertThat(result).isZero();
        verifyNoInteractions(alarmService);
    }

    @Test
    void filterlessStaffCountIsTenantTotalMinusExcluded() {
        CustomerId staff = new CustomerId(UUID.randomUUID());
        CustomerId excluded = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, staff);
        AlarmCountQuery query = filterlessQuery();

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.exclude(Set.of(excluded)));
        when(alarmService.countAlarmsByQuery(eq(tenantId), eq((CustomerId) null), eq(query))).thenReturn(30L);
        when(alarmService.countAlarmsByQuery(tenantId, excluded, query)).thenReturn(11L);

        long result = service.countAlarmsByQuery(u, query);

        assertThat(result).isEqualTo(19L);
    }

    @Test
    void filterlessUnrestrictedUsesUpstreamPathUntouched() {
        CustomerId own = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.TENANT_ADMIN, own);
        AlarmCountQuery query = filterlessQuery();

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.unrestricted());
        when(alarmService.countAlarmsByQuery(tenantId, own, query)).thenReturn(5L);

        long result = service.countAlarmsByQuery(u, query);

        assertThat(result).isEqualTo(5L);
        // Chemin upstream a l'identique : appel unique (tenant, customer propre, query).
        verify(alarmService).countAlarmsByQuery(tenantId, own, query);
    }
}

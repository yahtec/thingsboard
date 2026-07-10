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

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.DeviceId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.common.data.security.Authority;
import org.thingsboard.server.dao.alarm.AlarmService;
import org.thingsboard.server.dao.entity.EntityService;
import org.thingsboard.server.service.security.model.SecurityUser;
import org.thingsboard.server.service.security.scope.AccessScope;
import org.thingsboard.server.service.security.scope.AccessScopeService;
import org.thingsboard.server.service.ws.WebSocketService;
import org.thingsboard.server.service.ws.WebSocketSessionRef;
import org.thingsboard.server.service.ws.telemetry.cmd.v2.AlarmStatusCmd;
import org.thingsboard.server.service.ws.telemetry.cmd.v2.AlarmStatusUpdate;
import org.thingsboard.server.service.ws.telemetry.cmd.v2.CmdUpdate;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Couvre le controle de scope de la souscription WebSocket au statut d'alarme (finding I4).
 *
 * <p>Avant le fix, {@code handleCmd(AlarmStatusCmd)} ouvrait une souscription sur
 * {@code cmd.getOriginatorId()} sans aucun controle : un PARTY recevait le statut d'alarme live de
 * n'importe quel device du tenant. On verifie ici le cablage du handler autour de la decision
 * (testee exhaustivement dans {@code ScopedAlarmStatusTest}) :
 * <ul>
 *   <li>user scope hors perimetre =&gt; refus (AlarmStatusUpdate active=false, aucune souscription) ;</li>
 *   <li>user scope dans le perimetre =&gt; souscription creee ;</li>
 *   <li>UNRESTRICTED =&gt; inchange, l'owner n'est meme pas resolu (byte-identique).</li>
 * </ul>
 */
@ExtendWith(MockitoExtension.class)
class DefaultTbEntityDataSubscriptionServiceAlarmStatusScopeTest {

    @Mock
    WebSocketService wsService;

    @Mock
    EntityService entityService;

    @Mock
    AccessScopeService accessScopeService;

    @Mock
    AlarmService alarmService;

    @Mock
    TbLocalSubscriptionService localSubscriptionService;

    @InjectMocks
    DefaultTbEntityDataSubscriptionService service;

    private final TenantId tenantId = new TenantId(UUID.randomUUID());
    private final DeviceId originator = new DeviceId(UUID.randomUUID());
    private final int cmdId = 7;

    private SecurityUser user(Authority authority, CustomerId customerId) {
        SecurityUser u = new SecurityUser(new UserId(UUID.randomUUID()));
        u.setAuthority(authority);
        u.setTenantId(tenantId);
        u.setCustomerId(customerId);
        return u;
    }

    private WebSocketSessionRef session(SecurityUser u) {
        return WebSocketSessionRef.builder()
                .sessionId("session-" + UUID.randomUUID())
                .securityCtx(u)
                .build();
    }

    private AlarmStatusCmd cmd() {
        return new AlarmStatusCmd(cmdId, originator, null, null);
    }

    @Test
    void partyOutOfScopeOriginatorIsRefusedWithoutSubscription() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        CustomerId siteInScope = new CustomerId(UUID.randomUUID());
        CustomerId siteOfOriginator = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, party);
        WebSocketSessionRef session = session(u);

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.include(Set.of(siteInScope)));
        when(entityService.fetchEntityCustomerId(tenantId, originator)).thenReturn(Optional.of(siteOfOriginator));

        service.handleCmd(session, cmd());

        ArgumentCaptor<CmdUpdate> captor = ArgumentCaptor.forClass(CmdUpdate.class);
        then(wsService).should().sendUpdate(eq(session.getSessionId()), captor.capture());
        CmdUpdate update = captor.getValue();
        assertThat(update).isInstanceOf(AlarmStatusUpdate.class);
        assertThat(update.getCmdId()).isEqualTo(cmdId);
        assertThat(((AlarmStatusUpdate) update).isActive()).isFalse();
        // Aucune souscription ne doit etre creee pour un originator hors perimetre.
        verifyNoInteractions(localSubscriptionService);
        // On ne consulte jamais la table d'alarmes pour un refus.
        verifyNoInteractions(alarmService);
    }

    @Test
    void partyUnresolvedOriginatorIsRefusedFailClosed() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        CustomerId siteInScope = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, party);
        WebSocketSessionRef session = session(u);

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.include(Set.of(siteInScope)));
        when(entityService.fetchEntityCustomerId(tenantId, originator)).thenReturn(Optional.empty());

        service.handleCmd(session, cmd());

        then(wsService).should().sendUpdate(eq(session.getSessionId()), any(AlarmStatusUpdate.class));
        verifyNoInteractions(localSubscriptionService);
        verifyNoInteractions(alarmService);
    }

    @Test
    void partyInScopeOriginatorCreatesSubscription() {
        CustomerId party = new CustomerId(UUID.randomUUID());
        CustomerId site = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.CUSTOMER_USER, party);
        WebSocketSessionRef session = session(u);

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.include(Set.of(site)));
        when(entityService.fetchEntityCustomerId(tenantId, originator)).thenReturn(Optional.of(site));
        when(alarmService.findActiveOriginatorAlarms(eq(tenantId), any(), anyInt())).thenReturn(List.of());

        service.handleCmd(session, cmd());

        // Une souscription est bien creee (l'originator est dans le portefeuille).
        then(localSubscriptionService).should().addSubscription(any(TbSubscription.class), eq(session));
    }

    @Test
    void tenantAdminIsUnchangedAndDoesNotResolveOwner() {
        CustomerId own = new CustomerId(UUID.randomUUID());
        SecurityUser u = user(Authority.TENANT_ADMIN, own);
        WebSocketSessionRef session = session(u);

        when(accessScopeService.resolve(u)).thenReturn(AccessScope.unrestricted());
        when(alarmService.findActiveOriginatorAlarms(eq(tenantId), any(), anyInt())).thenReturn(List.of());

        service.handleCmd(session, cmd());

        // UNRESTRICTED : comportement upstream inchange, on cree la souscription...
        then(localSubscriptionService).should().addSubscription(any(TbSubscription.class), eq(session));
        // ...et on ne resout JAMAIS l'owner de l'originator (byte-identique, pas de lecture DB en plus).
        verifyNoInteractions(entityService);
        // Le scope est resolu exactement une fois (court-circuit UNRESTRICTED), pas plus : on ne
        // re-consulte pas accessScopeService une seconde fois derriere (par ex. pour un check canView
        // redondant, qui de toute facon n'existe pas dans le handler — canView() est appele sur
        // l'AccessScope resolu, pas sur accessScopeService lui-meme).
        then(accessScopeService).should().resolve(u);
    }
}

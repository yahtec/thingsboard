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

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.transaction.event.TransactionalEventListenerFactory;
import org.thingsboard.server.common.data.Customer;
import org.thingsboard.server.common.data.User;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.UserId;
import org.thingsboard.server.dao.eventsourcing.SaveEntityEvent;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

/**
 * Test de DÉLIVRANCE Spring réelle (par opposition aux appels directs de
 * {@link ScopeCacheInvalidationListenerTest}).
 *
 * <p>Le bug I1 était invisible aux tests d'appel direct : un
 * {@code @TransactionalEventListener} typé {@code SaveEntityEvent<User>} n'est
 * JAMAIS invoqué par Spring, car {@link SaveEntityEvent} n'implémente pas
 * {@code ResolvableTypeProvider} et est publié en type brut. Spring ne peut
 * résoudre le générique au moment du publish → la signature {@code <User>}
 * n'est pas assignable depuis l'évènement brut, alors que {@code <?>} l'est.</p>
 *
 * <p>On monte un {@link AnnotationConfigApplicationContext} minimal (pas de
 * {@code @SpringBootTest}) contenant :
 * <ul>
 *   <li>un {@link TransactionalEventListenerFactory} pour que
 *       {@code @TransactionalEventListener} soit réellement pris en charge
 *       (hors transaction + {@code fallbackExecution=true} ⇒ délivrance
 *       synchrone immédiate) ;</li>
 *   <li>le listener sous test, avec un {@link AccessScopeService} mocké.</li>
 * </ul>
 * On publie ensuite un {@code SaveEntityEvent} BRUT (comme
 * {@code UserServiceImpl.saveUser}) portant un User et on vérifie
 * l'invalidation.</p>
 */
class ScopeCacheInvalidationSpringDeliveryTest {

    private AnnotationConfigApplicationContext ctx;
    private AccessScopeService accessScopeService;

    private final TenantId tenantId = new TenantId(UUID.randomUUID());
    private final CustomerId customerA = new CustomerId(UUID.randomUUID());

    @BeforeEach
    void setUp() {
        accessScopeService = mock(AccessScopeService.class);
        ctx = new AnnotationConfigApplicationContext();
        ctx.registerBean(AccessScopeService.class, () -> accessScopeService);
        ctx.registerBean(TransactionalEventListenerFactory.class);
        ctx.registerBean(ScopeCacheInvalidationListener.class);
        ctx.refresh();
    }

    @AfterEach
    void tearDown() {
        if (ctx != null) {
            ctx.close();
        }
    }

    /**
     * Le test qui échoue en ROUGE avec la signature {@code SaveEntityEvent<User>}
     * et passe en VERT avec {@code SaveEntityEvent<?>} : c'est la délivrance
     * réelle par Spring, impossible à simuler par un appel direct.
     */
    @Test
    void rawSaveEntityEventCarryingUserIsDeliveredAndInvalidatesScope() {
        User user = buildUser(customerA);
        // Publié EXACTEMENT comme UserServiceImpl : builder brut, aucun <User>.
        SaveEntityEvent<?> event = SaveEntityEvent.builder()
                .tenantId(tenantId).entity(user).entityId(user.getId()).build();

        ctx.publishEvent(event);

        verify(accessScopeService).invalidate(customerA);
    }

    /**
     * Un évènement portant une entité non-User (ici un Customer) ne doit pas
     * invalider le scope même s'il est bien délivré au listener {@code <?>}.
     */
    @Test
    void rawSaveEntityEventCarryingNonUserDoesNotInvalidate() {
        Customer customer = new Customer(new CustomerId(UUID.randomUUID()));
        SaveEntityEvent<?> event = SaveEntityEvent.builder()
                .tenantId(tenantId).entity(customer).entityId(customer.getId()).build();

        ctx.publishEvent(event);

        verify(accessScopeService, never()).invalidate(customerA);
    }

    /**
     * Sonde de contrôle : prouve la cause racine directement, indépendamment du
     * listener sous test. Deux handlers {@code @EventListener} sont enregistrés,
     * l'un typé {@code SaveEntityEvent<User>}, l'autre {@code SaveEntityEvent<?>} ;
     * on publie un évènement brut portant un User. Seul le handler {@code <?>}
     * le reçoit — exactement le piège de generics du bug I1.
     */
    @Test
    void wildcardHandlerReceivesRawEventButTypedHandlerDoesNot() {
        try (AnnotationConfigApplicationContext probeCtx = new AnnotationConfigApplicationContext()) {
            probeCtx.registerBean(GenericsProbe.class);
            probeCtx.refresh();
            GenericsProbe probe = probeCtx.getBean(GenericsProbe.class);

            User user = buildUser(customerA);
            probeCtx.publishEvent(SaveEntityEvent.builder()
                    .tenantId(tenantId).entity(user).entityId(user.getId()).build());

            assertThat(probe.wildcardHits.get())
                    .as("un handler SaveEntityEvent<?> DOIT recevoir l'évènement brut").isEqualTo(1);
            assertThat(probe.userTypedHits.get())
                    .as("un handler SaveEntityEvent<User> ne DOIT PAS recevoir l'évènement brut (bug I1)").isZero();
        }
    }

    /** Bean sonde : deux handlers annotés démontrant la résolution de generics. */
    static class GenericsProbe {
        final AtomicInteger wildcardHits = new AtomicInteger();
        final AtomicInteger userTypedHits = new AtomicInteger();

        @EventListener
        public void onWildcard(SaveEntityEvent<?> event) {
            wildcardHits.incrementAndGet();
        }

        @EventListener
        public void onUserTyped(SaveEntityEvent<User> event) {
            userTypedHits.incrementAndGet();
        }
    }

    private User buildUser(CustomerId customerId) {
        User user = new User();
        user.setId(new UserId(UUID.randomUUID()));
        user.setTenantId(tenantId);
        user.setCustomerId(customerId);
        return user;
    }
}

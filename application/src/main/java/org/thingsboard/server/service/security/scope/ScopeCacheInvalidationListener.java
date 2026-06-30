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

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.thingsboard.server.common.data.User;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.EntityId;
import org.thingsboard.server.common.data.relation.EntityRelation;
import org.thingsboard.server.dao.eventsourcing.RelationActionEvent;
import org.thingsboard.server.dao.eventsourcing.SaveEntityEvent;

/**
 * Invalide le cache {@link AccessScopeService} lorsque les relations de portefeuille
 * (CanView / Excluded entre customers) ou le profil d'un utilisateur changent.
 *
 * <p>Utilise {@code fallbackExecution = true} pour capturer les événements publiés
 * hors transaction (ex: batch asynchrone), identiquement à
 * {@code EdgeEventSourcingListener}.</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ScopeCacheInvalidationListener {

    private final AccessScopeService accessScopeService;

    /**
     * Invalide le scope du customer source lorsqu'une relation portfolio
     * (CAN_VIEW ou EXCLUDED) est créée ou supprimée.
     *
     * <p>Seules les relations dont le {@code from} est un CUSTOMER sont
     * pertinentes — ce sont les relations que {@link DefaultAccessScopeService#targets}
     * lit pour calculer le scope.</p>
     */
    @TransactionalEventListener(fallbackExecution = true)
    public void handleRelationEvent(RelationActionEvent event) {
        EntityRelation relation = event.getRelation();
        if (relation == null) {
            return;
        }
        String type = relation.getType();
        if (!PortfolioAccess.CAN_VIEW.equals(type) && !PortfolioAccess.EXCLUDED.equals(type)) {
            return;
        }
        EntityId from = relation.getFrom();
        if (from != null && from.getEntityType() == EntityType.CUSTOMER) {
            CustomerId customerId = new CustomerId(from.getId());
            log.debug("[{}] Invalidating scope cache for customer {} after relation {} event (type={})",
                    event.getTenantId(), customerId, event.getActionType(), type);
            accessScopeService.invalidate(customerId);
        }
    }

    /**
     * Invalide le scope du customer propriétaire d'un utilisateur dont le
     * profil vient d'être modifié (changement de rôle portfolioRole possible).
     */
    @TransactionalEventListener(fallbackExecution = true)
    public void handleUserSaveEvent(SaveEntityEvent<User> event) {
        User user = event.getEntity();
        if (user == null) {
            return;
        }
        CustomerId customerId = user.getCustomerId();
        if (customerId == null || customerId.isNullUid()) {
            return;
        }
        log.debug("[{}] Invalidating scope cache for customer {} after user {} save",
                event.getTenantId(), customerId, user.getId());
        accessScopeService.invalidate(customerId);
    }
}

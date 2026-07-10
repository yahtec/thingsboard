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
package org.thingsboard.server.dao.sql.query;

import org.junit.jupiter.api.Test;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.permission.CustomerScopeMode;
import org.thingsboard.server.common.data.permission.QueryContext;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Tests unitaires de la clause de permission SQL générée par {@link DefaultEntityQueryRepository}
 * pour la couche scope multi-customer (I2b / M1). Ces tests n'exigent pas de base (pas de @DaoSqlTest) :
 * ils comparent la chaîne WHERE produite par {@code defaultPermissionQuery} pour chaque combinaison
 * type-de-requête × mode × liste vide/non vide.
 */
class DefaultEntityQueryRepositoryScopeSqlTest {

    private static final String ALLOWLIST = "'DEVICE','ASSET','ENTITY_VIEW','EDGE'";

    private final DefaultEntityQueryRepository repo = new DefaultEntityQueryRepository(null, null, null);
    private final TenantId tenantId = new TenantId(UUID.randomUUID());
    private final CustomerId own = new CustomerId(UUID.randomUUID());

    private SqlQueryContext ctx(EntityType rootType, CustomerId ownCustomerId, List<UUID> ids, CustomerScopeMode mode) {
        return new SqlQueryContext(new QueryContext(tenantId, ownCustomerId, rootType, ids, mode));
    }

    // ── I2b : requête RELATIONS scopée = filtrage PAR LIGNE (allowlisté vs own-customer) ──────────

    @Test
    void relationsIncludeNonEmpty_perRowTypeCase() {
        List<UUID> ids = List.of(UUID.randomUUID(), UUID.randomUUID());
        SqlQueryContext ctx = ctx(EntityType.ASSET, own, ids, CustomerScopeMode.INCLUDE);
        String where = repo.defaultPermissionQuery(ctx, true);

        assertThat(where).isEqualTo("e.tenant_id=:permissions_tenant_id and ("
                + "(e.entity_type in (" + ALLOWLIST + ") and (e.customer_id in (:permissions_customer_ids)))"
                + " or (e.entity_type not in (" + ALLOWLIST + ") and (e.customer_id = :permissions_own_customer_id)))");
        assertThat(ctx.hasValue("permissions_customer_ids")).isTrue();
        assertThat(ctx.hasValue("permissions_own_customer_id")).isTrue();
    }

    @Test
    void relationsIncludeEmpty_deniesAllowlistedButKeepsOwnCustomerFallback() {
        SqlQueryContext ctx = ctx(EntityType.ASSET, own, List.of(), CustomerScopeMode.INCLUDE);
        String where = repo.defaultPermissionQuery(ctx, true);

        assertThat(where).isEqualTo("e.tenant_id=:permissions_tenant_id and ("
                + "(e.entity_type in (" + ALLOWLIST + ") and (1=0))"
                + " or (e.entity_type not in (" + ALLOWLIST + ") and (e.customer_id = :permissions_own_customer_id)))");
        // deny-by-default sur les types allowlistés, pas de paramètre de liste
        assertThat(ctx.hasValue("permissions_customer_ids")).isFalse();
    }

    @Test
    void relationsExcludeNonEmpty_perRowTypeCase() {
        List<UUID> ids = List.of(UUID.randomUUID());
        SqlQueryContext ctx = ctx(EntityType.ASSET, own, ids, CustomerScopeMode.EXCLUDE);
        String where = repo.defaultPermissionQuery(ctx, true);

        assertThat(where).isEqualTo("e.tenant_id=:permissions_tenant_id and ("
                + "(e.entity_type in (" + ALLOWLIST + ") and (e.customer_id not in (:permissions_customer_ids)))"
                + " or (e.entity_type not in (" + ALLOWLIST + ") and (e.customer_id = :permissions_own_customer_id)))");
    }

    @Test
    void relationsExcludeEmpty_allowsAllowlistedKeepsOwnCustomerFallback() {
        SqlQueryContext ctx = ctx(EntityType.ASSET, own, List.of(), CustomerScopeMode.EXCLUDE);
        String where = repo.defaultPermissionQuery(ctx, true);

        assertThat(where).isEqualTo("e.tenant_id=:permissions_tenant_id and ("
                + "(e.entity_type in (" + ALLOWLIST + ") and (1=1))"
                + " or (e.entity_type not in (" + ALLOWLIST + ") and (e.customer_id = :permissions_own_customer_id)))");
        assertThat(ctx.hasValue("permissions_customer_ids")).isFalse();
    }

    @Test
    void relationsWithoutOwnCustomer_failsClosedForNonAllowlisted() {
        List<UUID> ids = List.of(UUID.randomUUID());
        SqlQueryContext ctx = ctx(EntityType.ASSET, null, ids, CustomerScopeMode.INCLUDE);
        String where = repo.defaultPermissionQuery(ctx, true);

        assertThat(where).isEqualTo("e.tenant_id=:permissions_tenant_id and ("
                + "(e.entity_type in (" + ALLOWLIST + ") and (e.customer_id in (:permissions_customer_ids)))"
                + " or (e.entity_type not in (" + ALLOWLIST + ") and (1=0)))");
        assertThat(ctx.hasValue("permissions_own_customer_id")).isFalse();
    }

    // ── M1 : cohérence DASHBOARD (non allowlisté) exclusion vide vs non vide ─────────────────────
    //
    // Un dashboard a SELECT_CUSTOMER_ID = NULL. La branche non-allowlistée applique
    // `e.customer_id = :permissions_own_customer_id` → NULL = X est toujours faux, donc le dashboard
    // est exclu de façon IDENTIQUE que la liste d'exclusion soit vide ou non (fin du piège NOT IN + NULL).

    @Test
    void dashboardBranchIsIdenticalWhetherExcludedEmptyOrNot() {
        String emptyBranch = nonAllowlistedBranch(repo.defaultPermissionQuery(
                ctx(EntityType.ASSET, own, List.of(), CustomerScopeMode.EXCLUDE), true));
        String nonEmptyBranch = nonAllowlistedBranch(repo.defaultPermissionQuery(
                ctx(EntityType.ASSET, own, List.of(UUID.randomUUID()), CustomerScopeMode.EXCLUDE), true));

        assertThat(emptyBranch)
                .isEqualTo(nonEmptyBranch)
                .isEqualTo("(e.entity_type not in (" + ALLOWLIST + ") and (e.customer_id = :permissions_own_customer_id))");
    }

    private static String nonAllowlistedBranch(String where) {
        int idx = where.indexOf(" or (e.entity_type not in");
        return where.substring(idx + 4, where.length() - 1); // retire le " or " initial et la ")" finale du groupe global
    }

    // ── Non-relations (recherches DEVICE/ASSET/…) : filtre PLAT inchangé (octet-identique) ───────

    @Test
    void flatIncludeEmpty_denyByDefault() {
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DEVICE, own, List.of(), CustomerScopeMode.INCLUDE), false))
                .isEqualTo("e.tenant_id=:permissions_tenant_id and 1=0");
    }

    @Test
    void flatIncludeNonEmpty() {
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DEVICE, own, List.of(UUID.randomUUID()), CustomerScopeMode.INCLUDE), false))
                .isEqualTo("e.tenant_id=:permissions_tenant_id and e.customer_id in (:permissions_customer_ids)");
    }

    @Test
    void flatExcludeEmpty() {
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DEVICE, own, List.of(), CustomerScopeMode.EXCLUDE), false))
                .isEqualTo("e.tenant_id=:permissions_tenant_id");
    }

    @Test
    void flatExcludeNonEmpty() {
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DEVICE, own, List.of(UUID.randomUUID()), CustomerScopeMode.EXCLUDE), false))
                .isEqualTo("e.tenant_id=:permissions_tenant_id and e.customer_id not in (:permissions_customer_ids)");
    }

    // ── Branche legacy (UNRESTRICTED) : le flag relations ne doit RIEN changer ────────────────────

    @Test
    void legacyOwnCustomerUnchangedByRelationsFlag() {
        String expected = "e.tenant_id=:permissions_tenant_id and e.customer_id=:permissions_customer_id";
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DEVICE, own, null, CustomerScopeMode.UNRESTRICTED), true))
                .isEqualTo(expected);
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DEVICE, own, null, CustomerScopeMode.UNRESTRICTED), false))
                .isEqualTo(expected);
    }

    @Test
    void legacyCustomerEntityUnchanged() {
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.CUSTOMER, own, null, CustomerScopeMode.UNRESTRICTED), true))
                .isEqualTo("e.tenant_id=:permissions_tenant_id and e.id=:permissions_customer_id");
    }

    @Test
    void legacyDashboardUnchanged() {
        assertThat(repo.defaultPermissionQuery(ctx(EntityType.DASHBOARD, own, null, CustomerScopeMode.UNRESTRICTED), true))
                .isEqualTo("e.tenant_id=:permissions_tenant_id and e.assigned_customers like concat('%', :permissions_customer_id, '%')");
    }
}

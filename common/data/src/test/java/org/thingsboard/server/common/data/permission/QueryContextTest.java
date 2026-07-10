package org.thingsboard.server.common.data.permission;

import org.junit.jupiter.api.Test;
import org.thingsboard.server.common.data.EntityType;
import org.thingsboard.server.common.data.id.CustomerId;
import org.thingsboard.server.common.data.id.TenantId;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class QueryContextTest {

    private final TenantId tenantId = new TenantId(UUID.randomUUID());

    @Test
    void legacyCtorDefaultsToUnrestricted() {
        QueryContext ctx = new QueryContext(tenantId, new CustomerId(UUID.randomUUID()), EntityType.DEVICE, false);
        assertThat(ctx.getScopeMode()).isEqualTo(CustomerScopeMode.UNRESTRICTED);
        assertThat(ctx.getCustomerIds()).isNull();
    }

    @Test
    void scopedCtorCarriesIncludeSet() {
        UUID a = UUID.randomUUID();
        QueryContext ctx = new QueryContext(tenantId, null, EntityType.DEVICE, List.of(a), CustomerScopeMode.INCLUDE);
        assertThat(ctx.getScopeMode()).isEqualTo(CustomerScopeMode.INCLUDE);
        assertThat(ctx.getCustomerIds()).containsExactly(a);
        assertThat(ctx.getCustomerId()).isNull();
    }

    @Test
    void scopedCtorCarriesOwnCustomerId() {
        UUID a = UUID.randomUUID();
        CustomerId own = new CustomerId(UUID.randomUUID());
        QueryContext ctx = new QueryContext(tenantId, own, EntityType.DEVICE, List.of(a), CustomerScopeMode.EXCLUDE);
        assertThat(ctx.getScopeMode()).isEqualTo(CustomerScopeMode.EXCLUDE);
        assertThat(ctx.getCustomerIds()).containsExactly(a);
        assertThat(ctx.getCustomerId()).isEqualTo(own);
    }
}

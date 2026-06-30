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

import org.thingsboard.server.common.data.id.CustomerId;

import java.util.Set;

public final class AccessScope {

    public enum Mode {
        UNRESTRICTED, INCLUDE, EXCLUDE
    }

    private final Mode mode;
    private final Set<CustomerId> customers;

    private AccessScope(Mode mode, Set<CustomerId> customers) {
        this.mode = mode;
        this.customers = customers;
    }

    public static AccessScope unrestricted() {
        return new AccessScope(Mode.UNRESTRICTED, Set.of());
    }

    public static AccessScope include(Set<CustomerId> customers) {
        return new AccessScope(Mode.INCLUDE, Set.copyOf(customers));
    }

    public static AccessScope exclude(Set<CustomerId> customers) {
        return new AccessScope(Mode.EXCLUDE, Set.copyOf(customers));
    }

    public Mode getMode() {
        return mode;
    }

    public Set<CustomerId> getCustomers() {
        return customers;
    }

    public boolean canView(CustomerId customerId) {
        switch (mode) {
            case UNRESTRICTED:
                return true;
            case INCLUDE:
                return customerId != null && customers.contains(customerId);
            case EXCLUDE:
                return customerId != null && !customers.contains(customerId);
            default:
                return false;
        }
    }
}

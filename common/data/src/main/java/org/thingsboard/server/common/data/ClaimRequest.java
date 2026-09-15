// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data;

import lombok.Data;
import lombok.ToString;

@Data
public class ClaimRequest {

    // Device claim key — possession allows transferring device ownership; excluded from toString.
    @ToString.Exclude
    private final String secretKey;

}

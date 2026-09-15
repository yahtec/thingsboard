// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.device.profile;

import lombok.Data;
import lombok.ToString;

@Data
public class ProvisionDeviceProfileCredentials {
    private final String provisionDeviceKey;
    @ToString.Exclude
    private final String provisionDeviceSecret;
}

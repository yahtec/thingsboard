// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.device.credentials;

import lombok.Data;
import lombok.ToString;

@Data
public class ProvisionDeviceCredentialsData {
    // Bearer secrets handed to the freshly-provisioned device — excluded from toString
    // because the provisioning path is log-rich and this object travels through it.
    @ToString.Exclude
    private final String token;
    private final String clientId;
    private final String username;
    @ToString.Exclude
    private final String password;
    private final String x509CertHash;
}

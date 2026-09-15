// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.device.credentials;

import lombok.Data;
import lombok.ToString;

@Data
public class BasicMqttCredentials {

    private String clientId;
    private String userName;
    // Excluded from toString — device MQTT passwords leak through any
    // `log.x("{}", basicMqttCredentials)` site, granting impersonation of the device.
    @ToString.Exclude
    private String password;

}

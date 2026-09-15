// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.rule.engine.credentials;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;
import lombok.ToString;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class BasicCredentials implements ClientCredentials {
    private String username;
    @ToString.Exclude
    private String password;

    @Override
    public CredentialsType getType() {
        return CredentialsType.BASIC;
    }
}

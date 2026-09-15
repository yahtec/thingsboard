// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.security;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;
import org.thingsboard.server.common.data.BaseDataWithAdditionalInfo;
import org.thingsboard.server.common.data.id.UserCredentialsId;
import org.thingsboard.server.common.data.id.UserId;

import java.io.Serial;

@Data
@EqualsAndHashCode(callSuper = true)
@ToString(callSuper = true)
public class UserCredentials extends BaseDataWithAdditionalInfo<UserCredentialsId> {

    @Serial
    private static final long serialVersionUID = -2108436378880529163L;

    private UserId userId;
    private boolean enabled;
    // Sensitive fields excluded from toString — they leak into TRACE/DEBUG logs through
    // statements like `log.trace("...{}", userCredentials)`. activateToken and resetToken
    // are bearer secrets granting direct account takeover; password is bcrypt-hashed but
    // still PII that should not appear in plaintext logs.
    @ToString.Exclude
    private String password;
    @ToString.Exclude
    private String activateToken;
    private Long activateTokenExpTime;
    @ToString.Exclude
    private String resetToken;
    private Long resetTokenExpTime;
    private Long lastLoginTs;
    private Integer failedLoginAttempts;

    public UserCredentials() {
        super();
    }

    public UserCredentials(UserCredentialsId id) {
        super(id);
    }


    @JsonIgnore
    public boolean isActivationTokenExpired() {
        return getActivationTokenTtl() == 0;
    }

    @JsonIgnore
    public long getActivationTokenTtl() {
        return activateTokenExpTime != null ? Math.max(activateTokenExpTime - System.currentTimeMillis(), 0) : 0;
    }

    @JsonIgnore
    public boolean isResetTokenExpired() {
        return getResetTokenTtl() == 0;
    }

    @JsonIgnore
    public long getResetTokenTtl() {
        return resetTokenExpTime != null ? Math.max(resetTokenExpTime - System.currentTimeMillis(), 0) : 0;
    }

}

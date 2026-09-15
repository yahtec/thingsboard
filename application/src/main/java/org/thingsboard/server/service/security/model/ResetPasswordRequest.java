// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.service.security.model;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.ToString;

@Schema
@Data
public class ResetPasswordRequest {

    // Both fields are secrets in transit (token = bearer that grants password reset;
    // new password = user-chosen plaintext). Spring MVC / controller advice loggers
    // sometimes dump the whole @RequestBody on validation errors — excluding here
    // ensures any `log.x("{}", req)` is safe by construction.
    @ToString.Exclude
    @Schema(description = "The reset token to verify", example = "AAB254FF67D..")
    private String resetToken;
    @ToString.Exclude
    @Schema(description = "The new password to set", example = "secret")
    private String password;
}

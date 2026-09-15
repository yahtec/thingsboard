// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.service.security.model;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.ToString;

@Schema
@Data
public class ChangePasswordRequest {

    @ToString.Exclude
    @Schema(description = "The old password", example = "OldPassword")
    private String currentPassword;
    @ToString.Exclude
    @Schema(description = "The new password", example = "NewPassword")
    private String newPassword;

}

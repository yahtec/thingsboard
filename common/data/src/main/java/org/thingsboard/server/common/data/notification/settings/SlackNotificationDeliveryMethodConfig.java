// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.notification.settings;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotEmpty;
import lombok.Data;
import lombok.ToString;
import org.thingsboard.server.common.data.notification.NotificationDeliveryMethod;

@Schema
@Data
public class SlackNotificationDeliveryMethodConfig implements NotificationDeliveryMethodConfig {

    // Excluded from toString — Slack bot tokens grant chat/file access scoped by the bot, no need to expose in logs.
    @NotEmpty
    @ToString.Exclude
    private String botToken;

    @Override
    public NotificationDeliveryMethod getMethod() {
        return NotificationDeliveryMethod.SLACK;
    }

}

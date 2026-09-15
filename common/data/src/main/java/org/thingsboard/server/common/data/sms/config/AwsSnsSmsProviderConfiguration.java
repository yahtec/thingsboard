// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.sms.config;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.ToString;

@Schema
@Data
public class AwsSnsSmsProviderConfiguration implements SmsProviderConfiguration {

    @Schema(description = "The AWS SNS Access Key ID.")
    private String accessKeyId;
    // Excluded from toString — leaking AWS secret access key grants programmatic access to the AWS account.
    @Schema(description = "The AWS SNS Access Key.")
    @ToString.Exclude
    private String secretAccessKey;
    @Schema(description = "The AWS region.")
    private String region;

    @Override
    public SmsProviderType getType() {
        return SmsProviderType.AWS_SNS;
    }

}

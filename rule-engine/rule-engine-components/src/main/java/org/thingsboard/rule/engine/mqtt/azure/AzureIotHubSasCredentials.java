// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.rule.engine.mqtt.azure;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import io.netty.handler.ssl.ClientAuth;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;
import lombok.extern.slf4j.Slf4j;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.thingsboard.common.util.AzureIotHubUtil;
import org.thingsboard.rule.engine.credentials.CertPemCredentials;
import org.thingsboard.rule.engine.credentials.CredentialsType;

import java.security.Security;

@Data
@EqualsAndHashCode(callSuper = true)
@Slf4j
@JsonIgnoreProperties(ignoreUnknown = true)
public class AzureIotHubSasCredentials extends CertPemCredentials {
    // Azure SAS key — bearer credential authenticating the rule node to the IoT Hub.
    @ToString.Exclude
    private String sasKey;

    @Override
    public SslContext initSslContext() {
        try {
            Security.addProvider(new BouncyCastleProvider());
            if (caCert == null || caCert.isEmpty()) {
                caCert = AzureIotHubUtil.getDefaultCaCert();
            }
            return SslContextBuilder.forClient()
                    .trustManager(createAndInitTrustManagerFactory())
                    .clientAuth(ClientAuth.REQUIRE)
                    .build();
        } catch (Exception e) {
            log.error("Creating Azure IoT Hub TLS factory failed!", e);
            throw new RuntimeException("Creating TLS factory failed!", e);
        }
    }

    @Override
    public CredentialsType getType() {
        return CredentialsType.SAS;
    }

}

/*
 * Copyright © 2016-2026 The Thingsboard Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.thingsboard.server.transport.mqtt;

import io.netty.handler.ssl.SslHandler;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;
import org.thingsboard.server.common.data.DeviceTransportType;
import org.thingsboard.server.common.data.StringUtils;
import org.thingsboard.server.common.transport.TransportService;
import org.thingsboard.server.common.transport.TransportServiceCallback;
import org.thingsboard.server.common.transport.auth.ValidateDeviceCredentialsResponse;
import org.thingsboard.server.common.transport.config.ssl.SslCredentials;
import org.thingsboard.server.common.transport.config.ssl.SslCredentialsConfig;
import org.thingsboard.server.common.transport.util.SslUtil;
import org.thingsboard.server.gen.transport.TransportProtos;

import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

@Slf4j
@Component("MqttSslHandlerProvider")
@TbMqttSslTransportComponent
public class MqttSslHandlerProvider implements SmartInitializingSingleton {

    @Value("${transport.mqtt.ssl.protocol}")
    private String sslProtocol;

    @Autowired
    private TransportService transportService;

    @Bean
    @ConfigurationProperties(prefix = "transport.mqtt.ssl.credentials")
    public SslCredentialsConfig mqttSslCredentials() {
        return new SslCredentialsConfig("MQTT SSL Credentials", false);
    }

    @Autowired
    @Qualifier("mqttSslCredentials")
    private SslCredentialsConfig mqttSslCredentialsConfig;

    private volatile SSLContext sslContext;
    private volatile String[] enabledProtocols;
    private volatile String[] enabledCipherSuites;

    @Override
    public void afterSingletonsInstantiated() {
        // Eagerly build the initial context so the handshake path is a lock-free
        // volatile read.
        this.sslContext = createSslContext();
        cacheEnabledProtocolsAndCiphers(this.sslContext);
        mqttSslCredentialsConfig.registerReloadCallback(() -> {
            log.info("MQTT SSL certificates reloaded. Rebuilding SSL context...");
            // Build the new context first; if it fails, the old one stays in place, and
            // the exception propagates to CertificateReloadManager's retry/backoff logic.
            SSLContext rebuilt = createSslContext();
            cacheEnabledProtocolsAndCiphers(rebuilt);
            this.sslContext = rebuilt;
            log.info("MQTT SSL context rebuilt. New connections will use the new certificate.");
        });
    }

    private void cacheEnabledProtocolsAndCiphers(SSLContext ctx) {
        // Compute once: supported protocols/ciphers don't vary at runtime, so allocating
        // a fresh ArrayList per handshake (thousands/sec on a busy broker) is pure waste.
        SSLEngine probe = ctx.createSSLEngine();
        this.enabledProtocols = filterEnabledProtocols(probe.getSupportedProtocols());
        this.enabledCipherSuites = filterEnabledCipherSuites(probe.getSupportedCipherSuites());
    }

    public SslHandler getSslHandler() {
        SSLContext ctx = sslContext;
        // Defensive lazy init in case afterSingletonsInstantiated hasn't run yet (e.g.,
        // test wiring).
        // In normal operation ctx is non-null here, so the handshake path is lock-free.
        if (ctx == null) {
            synchronized (this) {
                ctx = sslContext;
                if (ctx == null) {
                    ctx = createSslContext();
                    cacheEnabledProtocolsAndCiphers(ctx);
                    sslContext = ctx;
                }
            }
        }
        SSLEngine sslEngine = ctx.createSSLEngine();
        sslEngine.setUseClientMode(false);
        sslEngine.setNeedClientAuth(false);
        sslEngine.setWantClientAuth(true);
        sslEngine.setEnabledProtocols(enabledProtocols);
        sslEngine.setEnabledCipherSuites(enabledCipherSuites);
        sslEngine.setEnableSessionCreation(true);
        return new SslHandler(sslEngine);
    }

    private SSLContext createSslContext() {
        try {
            SslCredentials sslCredentials = this.mqttSslCredentialsConfig.getCredentials();
            TrustManagerFactory tmFactory = sslCredentials.createTrustManagerFactory();
            KeyManagerFactory kmf = sslCredentials.createKeyManagerFactory();

            KeyManager[] km = kmf.getKeyManagers();
            TrustManager x509wrapped = getX509TrustManager(tmFactory);
            TrustManager[] tm = { x509wrapped };
            String protocol = StringUtils.isEmpty(sslProtocol) ? "TLSv1.3" : sslProtocol;
            SSLContext sslContext = SSLContext.getInstance(protocol);
            sslContext.init(km, tm, null);
            return sslContext;
        } catch (Exception e) {
            log.error("Unable to set up SSL context. Reason: {}", e.getMessage(), e);
            throw new RuntimeException("Failed to get SSL context", e);
        }
    }

    static String[] filterEnabledProtocols(String[] supported) {
        java.util.List<String> kept = new java.util.ArrayList<>(supported.length);
        for (String p : supported) {
            if ("TLSv1.2".equals(p) || "TLSv1.3".equals(p)) {
                kept.add(p);
            }
        }
        return kept.toArray(new String[0]);
    }

    static String[] filterEnabledCipherSuites(String[] supported) {
        java.util.List<String> kept = new java.util.ArrayList<>(supported.length);
        for (String c : supported) {
            String upper = c.toUpperCase();
            if (upper.contains("_NULL_") || upper.contains("_ANON_") || upper.contains("_EXPORT_")
                    || upper.contains("_RC4_") || upper.contains("_DES_") || upper.contains("_3DES_")
                    || upper.contains("_MD5") || upper.contains("_IDEA_")) {
                continue;
            }
            kept.add(c);
        }
        return kept.toArray(new String[0]);
    }

    private TrustManager getX509TrustManager(TrustManagerFactory tmf) throws Exception {
        X509TrustManager x509Tm = null;
        for (TrustManager tm : tmf.getTrustManagers()) {
            if (tm instanceof X509TrustManager x509TrustManager) {
                x509Tm = x509TrustManager;
                break;
            }
        }
        if (x509Tm == null) {
            throw new IllegalStateException("TrustManagerFactory returned no X509TrustManager — check SSL credentials configuration");
        }
        return new ThingsboardMqttX509TrustManager(x509Tm, transportService);
    }

    static class ThingsboardMqttX509TrustManager implements X509TrustManager {

        private final X509TrustManager trustManager;
        private final TransportService transportService;

        ThingsboardMqttX509TrustManager(X509TrustManager trustManager, TransportService transportService) {
            this.trustManager = trustManager;
            this.transportService = transportService;
        }

        @Override
        public X509Certificate[] getAcceptedIssuers() {
            return trustManager.getAcceptedIssuers();
        }

        @Override
        public void checkServerTrusted(X509Certificate[] chain,
                String authType) throws CertificateException {
            trustManager.checkServerTrusted(chain, authType);
        }

        @Override
        public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            if (!validateCertificateChain(chain)) {
                throw new CertificateException("Invalid Chain of X509 Certificates. ");
            }
            String clientDeviceCertValue = SslUtil.getCertificateString(chain[0]);
            final String[] credentialsBodyHolder = new String[1];
            CountDownLatch latch = new CountDownLatch(1);
            try {
                String certificateChain = SslUtil.getCertificateChainString(chain);
                transportService.process(DeviceTransportType.MQTT,
                        TransportProtos.ValidateOrCreateDeviceX509CertRequestMsg
                                .newBuilder().setCertificateChain(certificateChain).build(),
                        new TransportServiceCallback<>() {
                            @Override
                            public void onSuccess(ValidateDeviceCredentialsResponse msg) {
                                if (!StringUtils.isEmpty(msg.getCredentials())) {
                                    credentialsBodyHolder[0] = msg.getCredentials();
                                }
                                latch.countDown();
                            }

                            @Override
                            public void onError(Throwable e) {
                                log.trace("Failed to process certificate chain", e);
                                latch.countDown();
                            }
                        });
                // F-5: transport service timeout is an explicit auth failure, not a pass.
                if (!latch.await(10, TimeUnit.SECONDS)) {
                    throw new CertificateException("Certificate validation timed out — transport service unavailable");
                }
                if (!clientDeviceCertValue.equals(credentialsBodyHolder[0])) {
                    log.debug("Failed to find credentials for device certificate");
                    if (chain.length == 1) {
                        throw new CertificateException("Invalid Device Certificate");
                    } else {
                        throw new CertificateException("Invalid Chain of X509 Certificates");
                    }
                }
            } catch (CertificateException ce) {
                // F-1: re-throw so the SSL layer rejects the handshake.
                throw ce;
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                throw new CertificateException("Certificate validation interrupted");
            } catch (Exception e) {
                log.error("Unexpected error during certificate validation: {}", e.getMessage(), e);
                throw new CertificateException("Certificate validation failed", e);
            }
        }

        private boolean validateCertificateChain(X509Certificate[] chain) {
            try {
                // F-3: verify validity period for every cert in the chain.
                for (X509Certificate cert : chain) {
                    cert.checkValidity();
                }
                if (chain.length > 1) {
                    X509Certificate leafCert = chain[0];
                    for (int i = 1; i < chain.length; i++) {
                        X509Certificate intermediateCert = chain[i];
                        leafCert.verify(intermediateCert.getPublicKey());
                        leafCert = intermediateCert;
                    }
                }
                return true;
            } catch (Exception e) {
                return false;
            }
        }

    }

}

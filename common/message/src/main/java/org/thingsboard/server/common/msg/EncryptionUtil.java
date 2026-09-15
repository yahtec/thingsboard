// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.msg;

import lombok.extern.slf4j.Slf4j;
import org.bouncycastle.crypto.digests.SHA3Digest;
import org.bouncycastle.util.encoders.Hex;

/**
 * @author Valerii Sosliuk
 */
@Slf4j
public class EncryptionUtil {

    private EncryptionUtil() {
    }

    // All needles are literal strings — replaceAll() interprets them as regex and recompiles
    // each one on every call. replace() does a literal substitution at ~10× the speed and
    // is on the X509 cert hashing path (called for every SSL handshake MQTT/CoAP/LwM2M).
    public static String certTrimNewLines(String input) {
        return input.replace("-----BEGIN CERTIFICATE-----", "")
                .replace("\n", "")
                .replace("\r", "")
                .replace("-----END CERTIFICATE-----", "");
    }

    public static String certTrimNewLinesForChainInDeviceProfile(String input) {
        return input.replace("\n", "")
                .replace("\r", "")
                .replace("-----BEGIN CERTIFICATE-----", "-----BEGIN CERTIFICATE-----\n")
                .replace("-----END CERTIFICATE-----", "\n-----END CERTIFICATE-----\n")
                .trim();
    }

    public static String pubkTrimNewLines(String input) {
        return input.replace("-----BEGIN PUBLIC KEY-----", "")
                .replace("\n", "")
                .replace("\r", "")
                .replace("-----END PUBLIC KEY-----", "");
    }

    public static String prikTrimNewLines(String input) {
        return input.replace("-----BEGIN EC PRIVATE KEY-----", "")
                .replace("\n", "")
                .replace("\r", "")
                .replace("-----END EC PRIVATE KEY-----", "");
    }


    public static String getSha3Hash(String data) {
        String trimmedData = certTrimNewLines(data);
        byte[] dataBytes = trimmedData.getBytes();
        SHA3Digest md = new SHA3Digest(256);
        md.reset();
        md.update(dataBytes, 0, dataBytes.length);
        byte[] hashedBytes = new byte[256 / 8];
        md.doFinal(hashedBytes, 0);
        String sha3Hash = Hex.toHexString(hashedBytes);
        return sha3Hash;
    }

    public static String getSha3Hash(String delim, String... tokens) {
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (String token : tokens) {
            if (token != null && !token.isEmpty()) {
                if (first) {
                    first = false;
                } else {
                    sb.append(delim);
                }
                sb.append(token);
            }
        }
        return getSha3Hash(sb.toString());
    }
}

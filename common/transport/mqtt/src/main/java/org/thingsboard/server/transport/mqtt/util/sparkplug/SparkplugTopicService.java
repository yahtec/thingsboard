/**
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
package org.thingsboard.server.transport.mqtt.util.sparkplug;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.thingsboard.server.common.data.exception.ThingsboardException;
import org.thingsboard.server.transport.mqtt.TbMqttTransportComponent;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import static org.thingsboard.server.transport.mqtt.util.sparkplug.SparkplugMessageType.STATE;
import static org.thingsboard.server.transport.mqtt.util.sparkplug.SparkplugTopic.parseTopic;

@Slf4j
@Service
@TbMqttTransportComponent
public class SparkplugTopicService {

    // Previously a plain HashMap — that's a data race when multiple Netty MQTT threads
    // publish concurrently (HashMap.resize() under contention can spin or corrupt the table).
    // It was also unbounded: a client publishing on random topic strings could grow the
    // cache without limit.
    //
    // Now: ConcurrentHashMap with a stop-inserting-when-full cap.
    //   - The cap is sized for the realistic upper bound of legit Sparkplug deployments
    //     (5000 devices × 3 message-type topics × headroom ≈ 50k).
    //   - When the cap is reached, new topics still parse correctly but are not cached.
    //     Legitimate entries that established the cache first stay hot, so steady-state
    //     performance is preserved even under a topic-flood attack.
    //   - Compared to the previous "clear on overflow" strategy, this avoids the
    //     thundering-herd cache miss that hit every publishing client after a flood.
    private static final int MAX_CACHE_SIZE = 50_000;
    private static final ConcurrentMap<String, SparkplugTopic> SPLIT_TOPIC_CACHE = new ConcurrentHashMap<>();
    public static final String TOPIC_ROOT_SPB_V_1_0 = "spBv1.0";
    public static final String TOPIC_ROOT_CERT_SP = "$sparkplug/certificates/";
    public static final String TOPIC_SPLIT_REGEXP = "/";
    public static final String TOPIC_STATE_REGEXP = TOPIC_ROOT_SPB_V_1_0 + TOPIC_SPLIT_REGEXP + STATE.name() + TOPIC_SPLIT_REGEXP;

    public static SparkplugTopic getSplitTopic(String topic) throws ThingsboardException {
        SparkplugTopic cached = SPLIT_TOPIC_CACHE.get(topic);
        if (cached != null) {
            return cached;
        }
        SparkplugTopic parsed = parseTopic(topic);
        // size() on ConcurrentHashMap is O(1) under low contention via baseCount + counter cells.
        if (SPLIT_TOPIC_CACHE.size() < MAX_CACHE_SIZE) {
            SparkplugTopic prior = SPLIT_TOPIC_CACHE.putIfAbsent(topic, parsed);
            return prior != null ? prior : parsed;
        }
        return parsed;
    }

    /**
     * all ID Element MUST be a UTF-8 string
     * and with the exception of the reserved characters of + (plus), / (forward slash).
     * Publish: $sparkplug/certificates/spBv1.0/G1/NBIRTH/E1
     * Publish: spBv1.0/G1/NBIRTH/E1
     * Publish: $sparkplug/certificates/spBv1.0/G1/DBIRTH/E1/D1
     * Publish: spBv1.0/G1/DBIRTH/E1/D1
     * @param topic
     * @return
     * @throws ThingsboardException
     */
    public static SparkplugTopic parseTopicPublish(String topic) throws ThingsboardException {
        topic = topic.startsWith(TOPIC_ROOT_CERT_SP) ? topic.substring(TOPIC_ROOT_CERT_SP.length()) : topic;
        topic = topic.indexOf("+") > 0 ? topic.substring(0, topic.indexOf("+")): topic;
        return getSplitTopic(topic);
    }
}


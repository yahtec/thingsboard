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
package org.thingsboard.server.common.data;

import lombok.extern.slf4j.Slf4j;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.Set;

@Slf4j
public class JavaSerDesUtil {

    /**
     * Exact class names rejected up-front. O(1) lookup, no prefix scan.
     */
    private static final Set<String> BLOCKED_CLASS_NAMES = Set.of(
            "java.lang.Runtime",
            "java.lang.ProcessBuilder",
            "java.lang.UNIXProcess",
            "java.lang.ProcessImpl",
            "com.sun.rowset.JdbcRowSetImpl",
            "javax.management.BadAttributeValueExpException",
            "javax.management.openmbean.CompositeDataSupport",
            "javax.script.ScriptEngineManager",
            "javax.naming.InitialContext",
            "javax.naming.spi.NamingManager",
            "javax.swing.UIDefaults$ProxyLazyValue",
            "sun.reflect.annotation.AnnotationInvocationHandler",
            "org.apache.commons.beanutils.BeanComparator",
            "org.apache.commons.fileupload.disk.DiskFileItem",
            "org.springframework.core.SerializableTypeWrapper",
            "org.springframework.aop.support.DefaultBeanFactoryPointcutAdvisor",
            "org.springframework.beans.factory.config.PropertyPathFactoryBean",
            "org.springframework.beans.factory.ObjectFactory",
            "org.springframework.aop.target.HotSwappableTargetSource",
            "org.springframework.context.support.ClassPathXmlApplicationContext",
            "org.springframework.context.support.FileSystemXmlApplicationContext",
            "org.hibernate.engine.spi.TypedValue",
            "org.hibernate.property.access.spi.GetterMethodImpl"
    );

    /**
     * Package/class prefixes rejected after the exact-match miss. Linear but kept short.
     * Ordered roughly by expected hit frequency.
     */
    private static final String[] BLOCKED_CLASS_PREFIXES = {
            "org.apache.commons.collections.functors.",
            "org.apache.commons.collections.keyvalue.",
            "org.apache.commons.collections4.functors.",
            "org.apache.commons.collections4.keyvalue.",
            "org.apache.commons.collections4.comparators.",
            "com.sun.org.apache.xalan.internal.xsltc.",
            "com.sun.org.apache.bcel.internal.util.",
            "org.apache.xalan.xsltc.",
            "org.hibernate.tuple.component.AbstractComponentTuplizer",
            "org.codehaus.groovy.runtime.",
            "clojure.lang.",
            "com.mchange.v2.c3p0.",
            "org.apache.tomcat.dbcp.",
            "org.apache.commons.dbcp.",
            "org.apache.commons.dbcp2.",
            "org.apache.openjpa.ee.",
            "com.atomikos.icatch.",
            "org.python.core.",
            "org.jboss.interceptor.proxy.",
            "java.rmi.server.UnicastRemote",
            "java.rmi.registry.",
            "javax.management.remote."
    };

    /**
     * Decision cache keyed by Class. The same handful of classes (User, Tenant, JwtPair,
     * notification protos, …) are deserialized over and over — caching the verdict turns
     * the per-class filter cost from ~3 µs (Set.contains + 25-prefix scan) into ~50 ns
     * (ClassValue lookup is lock-free and JIT-friendly). Memory is bounded by the number
     * of distinct serialized classes, which is small (dozens), and entries die with the
     * class loader they belong to.
     */
    private static final ClassValue<ObjectInputFilter.Status> CLASS_DECISIONS = new ClassValue<>() {
        @Override
        protected ObjectInputFilter.Status computeValue(Class<?> clazz) {
            String name = clazz.getName();
            if (clazz.isArray()) {
                Class<?> comp = clazz;
                while (comp.isArray()) comp = comp.getComponentType();
                if (comp.isPrimitive()) return ObjectInputFilter.Status.UNDECIDED;
                name = comp.getName();
            }
            if (BLOCKED_CLASS_NAMES.contains(name)) {
                return ObjectInputFilter.Status.REJECTED;
            }
            for (String prefix : BLOCKED_CLASS_PREFIXES) {
                if (name.startsWith(prefix)) {
                    return ObjectInputFilter.Status.REJECTED;
                }
            }
            return ObjectInputFilter.Status.UNDECIDED;
        }
    };

    private static final ObjectInputFilter SAFE_FILTER = info -> {
        // Structural limits — defense against zip-bombs and deep-recursion DoS during deserialization.
        // These are evaluated on every filter call (cheap: 4 long comparisons).
        if (info.depth() > 32) return ObjectInputFilter.Status.REJECTED;
        if (info.references() > 10_000) return ObjectInputFilter.Status.REJECTED;
        if (info.streamBytes() > 5_000_000) return ObjectInputFilter.Status.REJECTED;
        if (info.arrayLength() > 10_000) return ObjectInputFilter.Status.REJECTED;
        Class<?> clazz = info.serialClass();
        if (clazz == null) return ObjectInputFilter.Status.UNDECIDED;
        ObjectInputFilter.Status decision = CLASS_DECISIONS.get(clazz);
        if (decision == ObjectInputFilter.Status.REJECTED) {
            log.warn("Rejected deserialization of blocked class: {}", clazz.getName());
        }
        return decision;
    };

    @SuppressWarnings("unchecked")
    public static <T> T decode(byte[] byteArray) {
        if (byteArray == null || byteArray.length == 0) {
            return null;
        }
        InputStream is = new ByteArrayInputStream(byteArray);
        try (ObjectInputStream ois = new ObjectInputStream(is)) {
            ois.setObjectInputFilter(SAFE_FILTER);
            return (T) ois.readObject();
        } catch (InvalidClassException ice) {
            // The filter rejected a class — make the security event distinguishable from a corrupt stream.
            log.warn("Deserialization rejected by ObjectInputFilter: {}", ice.getMessage());
            return null;
        } catch (IOException | ClassNotFoundException e) {
            log.error("Error during deserialization", e);
            return null;
        }
    }

    public static <T> byte[] encode(T msq) {
        if (msq == null) {
            return null;
        }
        // Pre-size to skip the first 5 doublings (32 -> 1024) — encoded payloads are typically KB-sized.
        ByteArrayOutputStream boas = new ByteArrayOutputStream(1024);
        try (ObjectOutputStream ois = new ObjectOutputStream(boas)) {
            ois.writeObject(msq);
            return boas.toByteArray();
        } catch (IOException e) {
            log.error("Error during serialization", e);
            throw new RuntimeException(e);
        }
    }
}

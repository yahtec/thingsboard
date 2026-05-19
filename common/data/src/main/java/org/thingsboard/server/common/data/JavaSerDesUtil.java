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
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.Set;

@Slf4j
public class JavaSerDesUtil {

    /**
     * Conservative deny-list against known Java deserialization gadget chains (ysoserial / marshalsec families).
     * Plus structural limits to prevent zip-bombs and deep-recursion DoS.
     */
    private static final Set<String> BLOCKED_CLASS_PREFIXES = Set.of(
            "org.apache.commons.collections.functors.",
            "org.apache.commons.collections4.functors.",
            "org.apache.commons.beanutils.BeanComparator",
            "org.apache.commons.fileupload.disk.DiskFileItem",
            "com.sun.org.apache.xalan.internal.xsltc.",
            "com.sun.rowset.JdbcRowSetImpl",
            "com.sun.org.apache.bcel.internal.util.ClassLoader",
            "javax.management.BadAttributeValueExpException",
            "javax.management.openmbean.CompositeDataSupport",
            "javax.script.ScriptEngineManager",
            "java.lang.Runtime",
            "java.lang.ProcessBuilder",
            "java.rmi.server.UnicastRemoteObject",
            "java.rmi.registry.LocateRegistry",
            "org.springframework.core.SerializableTypeWrapper",
            "org.springframework.aop.support.DefaultBeanFactoryPointcutAdvisor",
            "org.springframework.beans.factory.config.PropertyPathFactoryBean",
            "org.springframework.context.support.ClassPathXmlApplicationContext",
            "org.springframework.context.support.FileSystemXmlApplicationContext",
            "org.hibernate.engine.spi.TypedValue",
            "org.hibernate.tuple.component.AbstractComponentTuplizer",
            "org.codehaus.groovy.runtime.ConvertedClosure",
            "org.codehaus.groovy.runtime.MethodClosure",
            "clojure.lang."
    );

    private static final ObjectInputFilter SAFE_FILTER = info -> {
        // Structural limits
        if (info.depth() > 32) return ObjectInputFilter.Status.REJECTED;
        if (info.references() > 10_000) return ObjectInputFilter.Status.REJECTED;
        if (info.streamBytes() > 5_000_000) return ObjectInputFilter.Status.REJECTED;
        if (info.arrayLength() > 10_000) return ObjectInputFilter.Status.REJECTED;
        Class<?> clazz = info.serialClass();
        if (clazz == null) return ObjectInputFilter.Status.UNDECIDED;
        String name = clazz.getName();
        if (clazz.isArray()) {
            Class<?> comp = clazz;
            while (comp.isArray()) comp = comp.getComponentType();
            if (comp.isPrimitive()) return ObjectInputFilter.Status.UNDECIDED;
            name = comp.getName();
        }
        for (String prefix : BLOCKED_CLASS_PREFIXES) {
            if (name.equals(prefix) || name.startsWith(prefix)) {
                log.warn("Rejected deserialization of blocked class: {}", name);
                return ObjectInputFilter.Status.REJECTED;
            }
        }
        return ObjectInputFilter.Status.UNDECIDED;
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
        } catch (IOException | ClassNotFoundException e) {
            log.error("Error during deserialization", e);
            return null;
        }
    }

    public static <T> byte[] encode(T msq) {
        if (msq == null) {
            return null;
        }
        ByteArrayOutputStream boas = new ByteArrayOutputStream();
        try (ObjectOutputStream ois = new ObjectOutputStream(boas)) {
            ois.writeObject(msq);
            return boas.toByteArray();
        } catch (IOException e) {
            log.error("Error during serialization", e);
            throw new RuntimeException(e);
        }
    }
}

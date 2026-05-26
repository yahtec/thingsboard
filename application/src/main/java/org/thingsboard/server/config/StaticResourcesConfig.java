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
package org.thingsboard.server.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Yahtec / TSmart: serve user-editable static files from a directory on disk.
 *
 * <p>Files placed in {@code ${tb.web.static-files-dir}} are served live at
 * {@code GET /static/**} — modifying or adding a file takes effect immediately,
 * with no Java recompile, no JAR rebuild and no server restart. Internal cache
 * is disabled (cachePeriod=0) so the next browser hit re-reads from disk.
 *
 * <p>Typical use case: per-installation synoptic pages (schemas, HTML overlays,
 * SVGs) referenced from dashboard widgets via {@code <iframe src="/static/...">}
 * or {@code <img src="/static/...">}. The admin uploads / edits files over
 * SSH/FTP/Samba on the host filesystem.
 *
 * <p>Configuration in {@code thingsboard.yml}:
 * <pre>
 * tb:
 *   web:
 *     static-files-dir: "${TB_STATIC_FILES_DIR:/usr/share/thingsboard/static/}"
 *     static-files-url-pattern: "${TB_STATIC_FILES_URL_PATTERN:/static/**}"
 * </pre>
 *
 * <p>If the configured directory does not exist at startup, this bean creates
 * it (best-effort). If creation fails the resource handler is still registered
 * — Spring will just 404 on requests until a file appears.
 *
 * <p><b>Security note:</b> the handler is mounted anonymously (no auth filter)
 * because typical assets here are public diagrams / illustrations. If you store
 * sensitive content under {@code /static/}, move it behind {@code /api/} (which
 * is auth-gated) or wrap this handler in your own controller with
 * {@code @PreAuthorize}.
 */
@Slf4j
@Configuration
public class StaticResourcesConfig implements WebMvcConfigurer {

    @Value("${tb.web.static-files-dir:/usr/share/thingsboard/static/}")
    private String staticFilesDir;

    @Value("${tb.web.static-files-url-pattern:/static/**}")
    private String staticFilesUrlPattern;

    @Value("${tb.web.static-files-enabled:true}")
    private boolean enabled;

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        if (!enabled) {
            log.info("Static files handler disabled via tb.web.static-files-enabled=false");
            return;
        }
        String location = normalizeLocation(staticFilesDir);
        try {
            Path dir = Paths.get(staticFilesDir);
            if (!Files.exists(dir)) {
                Files.createDirectories(dir);
                log.info("Created static files directory: {}", dir.toAbsolutePath());
            }
        } catch (Exception e) {
            // Non-fatal: the handler is still registered. If the directory is
            // mounted later (e.g. by an ops volume) it will start serving without restart.
            log.warn("Could not create static files directory '{}': {}. Handler still registered.",
                    staticFilesDir, e.getMessage());
        }
        log.info("Serving static files from {} at URL pattern {}", location, staticFilesUrlPattern);
        registry.addResourceHandler(staticFilesUrlPattern)
                .addResourceLocations(location)
                // cachePeriod=0 makes every request re-check the file timestamp,
                // so edits on disk are picked up by the next browser hit (after
                // its own browser cache expires — use Ctrl+F5 to bypass).
                .setCachePeriod(0);
    }

    /**
     * Spring's ResourceHandler requires either a classpath: prefix or a file:
     * URL that ends with a trailing slash. We normalise the user-provided path
     * to that form, accepting bare absolute paths ("/usr/share/...") as well as
     * already-prefixed strings ("file:/...").
     */
    private static String normalizeLocation(String raw) {
        if (raw == null || raw.isBlank()) {
            return "file:/usr/share/thingsboard/static/";
        }
        String trimmed = raw.trim();
        String urlForm = trimmed.startsWith("file:") || trimmed.startsWith("classpath:")
                ? trimmed
                : new File(trimmed).toURI().toString();
        return urlForm.endsWith("/") ? urlForm : urlForm + "/";
    }
}

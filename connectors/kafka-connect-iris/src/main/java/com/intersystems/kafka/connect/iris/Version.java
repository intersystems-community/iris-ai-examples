package com.intersystems.kafka.connect.iris;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Single source of truth for the value every {@code Connector.version()} in
 * this project reports back to the Kafka Connect framework.
 *
 * <p>The value comes from {@code kafka-connect-iris-version.properties},
 * which Maven resource-filters from {@code ${project.version}} at build
 * time (see the {@code <resources>} block in pom.xml). That keeps the
 * reported version wired to the actual build instead of a string someone
 * has to remember to bump by hand.
 */
public final class Version {

    private static final Logger log = LoggerFactory.getLogger(Version.class);
    private static final String VERSION_FILE = "/kafka-connect-iris-version.properties";
    private static final String UNKNOWN = "unknown";

    private static final String VERSION = readVersion();

    private Version() {
    }

    public static String get() {
        return VERSION;
    }

    private static String readVersion() {
        Properties props = new Properties();
        try (InputStream stream = Version.class.getResourceAsStream(VERSION_FILE)) {
            if (stream == null) {
                log.warn("Could not find {} on the classpath; reporting version as '{}'",
                        VERSION_FILE, UNKNOWN);
                return UNKNOWN;
            }
            props.load(stream);
        } catch (IOException e) {
            log.warn("Could not read {}; reporting version as '{}'", VERSION_FILE, UNKNOWN, e);
            return UNKNOWN;
        }
        String version = props.getProperty("version", UNKNOWN).trim();
        // Maven leaves the literal placeholder in place if this resource was
        // ever read without filtering having run (e.g. a raw `javac` on the
        // source tree rather than a full `mvn package`).
        if (version.isEmpty() || version.startsWith("${")) {
            return UNKNOWN;
        }
        return version;
    }
}

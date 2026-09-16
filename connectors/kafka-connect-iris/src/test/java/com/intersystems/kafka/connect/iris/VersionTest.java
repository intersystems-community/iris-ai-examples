package com.intersystems.kafka.connect.iris;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class VersionTest {

    @Test
    void reportsAFilteredVersionNotThePlaceholderOrUnknown() {
        String version = Version.get();
        // Deliberately not asserting the literal "0.1.0-SNAPSHOT" -- that
        // would keep passing even if Maven filtering silently broke and
        // Version fell back to a hardcoded default. What actually matters is
        // that resource filtering ran (no leftover "${...}") and produced
        // something that isn't the "I couldn't read the file" fallback.
        assertFalse(version.startsWith("$"), "resource filtering did not run: " + version);
        assertFalse(version.equalsIgnoreCase("unknown"), "version.properties was not found/readable");
        assertTrue(version.matches("\\d+\\.\\d+\\.\\d+(-SNAPSHOT)?"),
                "expected a semver-ish version, got: " + version);
    }
}

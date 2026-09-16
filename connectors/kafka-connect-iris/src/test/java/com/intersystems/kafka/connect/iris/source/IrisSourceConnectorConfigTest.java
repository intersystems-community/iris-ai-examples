package com.intersystems.kafka.connect.iris.source;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.config.ConfigException;
import org.junit.jupiter.api.Test;

class IrisSourceConnectorConfigTest {

    private static Map<String, String> baseProps() {
        Map<String, String> props = new HashMap<>();
        props.put(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:IRIS://localhost:1972/USER");
        props.put(IrisSourceConnectorConfig.TOPIC_PREFIX_CONFIG, "iris.");
        props.put(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG, "Patient,Encounter");
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "bulk");
        return props;
    }

    @Test
    void validBulkConfigParses() {
        assertDoesNotThrow(() -> new IrisSourceConnectorConfig(baseProps()));
    }

    @Test
    void rejectsUrlWithoutIrisScheme() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:mysql://localhost:3306/db");
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
        assertTrue(e.getMessage().contains("jdbc:IRIS:"), e.getMessage());
    }

    @Test
    void rejectsNeitherTableWhitelistNorQuery() {
        Map<String, String> props = baseProps();
        props.remove(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG);
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
        assertTrue(e.getMessage().contains("Exactly one of"), e.getMessage());
    }

    @Test
    void rejectsBothTableWhitelistAndQuery() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.QUERY_CONFIG, "SELECT * FROM Patient");
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
        assertTrue(e.getMessage().contains("Exactly one of"), e.getMessage());
    }

    @Test
    void incrementingModeRequiresIncrementingColumn() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "incrementing");
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
        assertTrue(e.getMessage().contains(IrisSourceConnectorConfig.INCREMENTING_COLUMN_CONFIG), e.getMessage());
    }

    @Test
    void timestampModeRequiresTimestampColumn() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "timestamp");
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
        assertTrue(e.getMessage().contains(IrisSourceConnectorConfig.TIMESTAMP_COLUMN_CONFIG), e.getMessage());
    }

    @Test
    void timestampIncrementingModeRequiresBothColumns() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "timestamp+incrementing");
        props.put(IrisSourceConnectorConfig.INCREMENTING_COLUMN_CONFIG, "id");
        // timestamp column deliberately left unset
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
        assertTrue(e.getMessage().contains(IrisSourceConnectorConfig.TIMESTAMP_COLUMN_CONFIG), e.getMessage());
    }

    @Test
    void rejectsUnknownMode() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "not-a-real-mode");
        assertThrows(ConfigException.class, () -> new IrisSourceConnectorConfig(props));
    }

    @Test
    void nonAutoInitialOffsetsDefaultToStartFromBeginning() {
        IrisSourceConnectorConfig config = new IrisSourceConnectorConfig(baseProps());
        assertEquals(-1L, config.getLong(IrisSourceConnectorConfig.INCREMENTING_INITIAL_CONFIG));
        assertEquals(-1L, config.getLong(IrisSourceConnectorConfig.TIMESTAMP_INITIAL_CONFIG));
    }

    @Test
    void operatorCanPinAnExplicitNonAutoStartingOffset() {
        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "incrementing");
        props.put(IrisSourceConnectorConfig.INCREMENTING_COLUMN_CONFIG, "id");
        props.put(IrisSourceConnectorConfig.INCREMENTING_INITIAL_CONFIG, "1000000");
        IrisSourceConnectorConfig config = new IrisSourceConnectorConfig(props);
        assertEquals(1_000_000L, config.getLong(IrisSourceConnectorConfig.INCREMENTING_INITIAL_CONFIG));
    }
}

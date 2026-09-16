package com.intersystems.kafka.connect.iris.sink;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.config.ConfigException;
import org.junit.jupiter.api.Test;

class IrisSinkConnectorConfigTest {

    private static Map<String, String> baseProps() {
        Map<String, String> props = new HashMap<>();
        props.put(IrisSinkConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:IRIS://localhost:1972/USER");
        props.put(IrisSinkConnectorConfig.TABLE_NAME_FORMAT_CONFIG, "${topic}");
        props.put(IrisSinkConnectorConfig.PK_FIELDS_CONFIG, "id");
        props.put(IrisSinkConnectorConfig.INSERT_MODE_CONFIG, "upsert");
        return props;
    }

    @Test
    void validUpsertConfigParses() {
        assertDoesNotThrow(() -> new IrisSinkConnectorConfig(baseProps()));
    }

    @Test
    void insertModeDoesNotRequirePkFields() {
        Map<String, String> props = baseProps();
        props.remove(IrisSinkConnectorConfig.PK_FIELDS_CONFIG);
        props.put(IrisSinkConnectorConfig.INSERT_MODE_CONFIG, "insert");
        assertDoesNotThrow(() -> new IrisSinkConnectorConfig(props));
    }

    @Test
    void upsertModeRequiresPkFields() {
        Map<String, String> props = baseProps();
        props.remove(IrisSinkConnectorConfig.PK_FIELDS_CONFIG);
        ConfigException e = assertThrows(ConfigException.class, () -> new IrisSinkConnectorConfig(props));
        assertTrue(e.getMessage().contains(IrisSinkConnectorConfig.PK_FIELDS_CONFIG), e.getMessage());
    }

    @Test
    void upsertNativeAlsoRequiresPkFields() {
        Map<String, String> props = baseProps();
        props.remove(IrisSinkConnectorConfig.PK_FIELDS_CONFIG);
        props.put(IrisSinkConnectorConfig.INSERT_MODE_CONFIG, "upsert_native");
        assertThrows(ConfigException.class, () -> new IrisSinkConnectorConfig(props));
    }

    @Test
    void rejectsUrlWithoutIrisScheme() {
        Map<String, String> props = baseProps();
        props.put(IrisSinkConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:postgresql://localhost:5432/db");
        assertThrows(ConfigException.class, () -> new IrisSinkConnectorConfig(props));
    }

    @Test
    void rejectsUnknownInsertMode() {
        Map<String, String> props = baseProps();
        props.put(IrisSinkConnectorConfig.INSERT_MODE_CONFIG, "not-a-real-mode");
        assertThrows(ConfigException.class, () -> new IrisSinkConnectorConfig(props));
    }

    @Test
    void upsertAliasResolvesToThePortableTestedStrategy() {
        IrisSinkConnectorConfig config = new IrisSinkConnectorConfig(baseProps());
        assertEquals(InsertMode.UPSERT_PORTABLE, config.insertMode());
    }

    @Test
    void batchSizeMustBePositive() {
        Map<String, String> props = baseProps();
        props.put(IrisSinkConnectorConfig.BATCH_SIZE_CONFIG, "0");
        assertThrows(ConfigException.class, () -> new IrisSinkConnectorConfig(props));
    }
}

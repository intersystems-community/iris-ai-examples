package com.intersystems.kafka.connect.iris.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class IrisSourceConnectorTest {

    private static Map<String, String> baseProps(String tables) {
        Map<String, String> props = new HashMap<>();
        props.put(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:IRIS://localhost:1972/USER");
        props.put(IrisSourceConnectorConfig.TOPIC_PREFIX_CONFIG, "iris.");
        props.put(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG, tables);
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "bulk");
        return props;
    }

    @Test
    void taskConfigsSplitsTablesAcrossTasks() {
        IrisSourceConnector connector = new IrisSourceConnector();
        connector.start(baseProps("T1,T2,T3,T4,T5"));

        List<Map<String, String>> configs = connector.taskConfigs(2);

        assertEquals(2, configs.size());
        String task0Tables = configs.get(0).get(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG);
        String task1Tables = configs.get(1).get(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG);
        assertEquals("T1,T3,T5", task0Tables);
        assertEquals("T2,T4", task1Tables);
    }

    @Test
    void taskConfigsNeverExceedsTableCountEvenIfMoreTasksAreRequested() {
        IrisSourceConnector connector = new IrisSourceConnector();
        connector.start(baseProps("T1,T2"));

        List<Map<String, String>> configs = connector.taskConfigs(10);

        assertEquals(2, configs.size(), "should not create idle tasks with no tables assigned");
    }

    @Test
    void queryModeAlwaysProducesExactlyOneTaskRegardlessOfMaxTasks() {
        IrisSourceConnector connector = new IrisSourceConnector();
        Map<String, String> props = new HashMap<>();
        props.put(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:IRIS://localhost:1972/USER");
        props.put(IrisSourceConnectorConfig.TOPIC_PREFIX_CONFIG, "iris.custom");
        props.put(IrisSourceConnectorConfig.QUERY_CONFIG, "SELECT * FROM Patient WHERE Active = 1");
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "bulk");
        connector.start(props);

        List<Map<String, String>> configs = connector.taskConfigs(8);
        assertEquals(1, configs.size());
    }

    @Test
    void versionIsWiredToTheBuild() {
        IrisSourceConnector connector = new IrisSourceConnector();
        assertNotNull(connector.version());
        assertEquals(false, connector.version().isBlank());
    }

    @Test
    void invalidConfigFailsFastOnStart() {
        IrisSourceConnector connector = new IrisSourceConnector();
        Map<String, String> badProps = baseProps("T1");
        badProps.put(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG, "not-a-jdbc-url");
        assertThrows(org.apache.kafka.common.config.ConfigException.class, () -> connector.start(badProps));
    }
}

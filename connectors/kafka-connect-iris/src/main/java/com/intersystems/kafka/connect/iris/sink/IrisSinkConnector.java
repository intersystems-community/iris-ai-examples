package com.intersystems.kafka.connect.iris.sink;

import com.intersystems.kafka.connect.iris.Version;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.apache.kafka.common.config.Config;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.common.config.ConfigException;
import org.apache.kafka.connect.connector.Task;
import org.apache.kafka.connect.sink.SinkConnector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Sink connector that writes records to IRIS tables. See {@link IrisSinkConnectorConfig}. */
public class IrisSinkConnector extends SinkConnector {

    private static final Logger log = LoggerFactory.getLogger(IrisSinkConnector.class);

    private Map<String, String> configProps;

    @Override
    public String version() {
        return Version.get();
    }

    @Override
    public void start(Map<String, String> props) {
        new IrisSinkConnectorConfig(props);
        this.configProps = props;
    }

    @Override
    public Class<? extends Task> taskClass() {
        return IrisSinkTask.class;
    }

    @Override
    public List<Map<String, String>> taskConfigs(int maxTasks) {
        // A sink task's partition assignment (which topic-partitions it consumes)
        // is handled by the Connect framework's consumer group, not by this method
        // -- unlike the source side, every sink task here runs identical config,
        // and the framework fans topic-partitions out across however many of
        // these identical tasks are requested.
        List<Map<String, String>> configs = new ArrayList<>();
        for (int i = 0; i < maxTasks; i++) {
            configs.add(configProps);
        }
        return configs;
    }

    @Override
    public void stop() {
        // No connector-level resources; each task owns its own connection.
    }

    @Override
    public ConfigDef config() {
        return IrisSinkConnectorConfig.CONFIG_DEF;
    }

    @Override
    public Config validate(Map<String, String> connectorConfigs) {
        Config config = super.validate(connectorConfigs);
        try {
            new IrisSinkConnectorConfig(connectorConfigs);
        } catch (ConfigException e) {
            log.debug("Cross-field validation failed: {}", e.getMessage());
            for (var value : config.configValues()) {
                if (value.name().equals(IrisSinkConnectorConfig.PK_FIELDS_CONFIG)
                        || value.name().equals(IrisSinkConnectorConfig.INSERT_MODE_CONFIG)) {
                    value.errorMessages().add(e.getMessage());
                }
            }
        }
        return config;
    }
}

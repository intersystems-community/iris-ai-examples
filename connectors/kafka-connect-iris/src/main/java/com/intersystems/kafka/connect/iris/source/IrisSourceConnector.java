package com.intersystems.kafka.connect.iris.source;

import com.intersystems.kafka.connect.iris.Version;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.apache.kafka.common.config.Config;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.connect.connector.Task;
import org.apache.kafka.connect.source.SourceConnector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * JDBC polling source connector for InterSystems IRIS.
 *
 * <p>See {@link IrisSourceConnectorConfig} for the full config surface and
 * {@link TableQuerier} / {@link TaskPartitioner} for how polling modes and
 * task partitioning are implemented -- both written specifically to answer
 * the community critique of IRIS's own built-in Kafka source adapters
 * (no real partition support, no non-auto offset handling; see this
 * connector's README for the citation).
 */
public class IrisSourceConnector extends SourceConnector {

    private static final Logger log = LoggerFactory.getLogger(IrisSourceConnector.class);

    private Map<String, String> configProps;

    @Override
    public String version() {
        return Version.get();
    }

    @Override
    public void start(Map<String, String> props) {
        // Constructing the config here, at connector start, is what makes
        // ConfigDef validation errors surface immediately (and with a
        // useful per-field message) instead of only on the first task
        // failing to start.
        new IrisSourceConnectorConfig(props);
        this.configProps = props;
    }

    @Override
    public Class<? extends Task> taskClass() {
        return IrisSourceTask.class;
    }

    @Override
    public List<Map<String, String>> taskConfigs(int maxTasks) {
        IrisSourceConnectorConfig config = new IrisSourceConnectorConfig(configProps);
        List<Map<String, String>> configs = new ArrayList<>();

        if (config.isQueryMode()) {
            // A single arbitrary query cannot be safely split across tasks;
            // see TableQuerier's javadoc. Exactly one task, regardless of maxTasks.
            configs.add(configProps);
            return configs;
        }

        List<String> tables = config.getList(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG);
        List<List<String>> groups = TaskPartitioner.partition(tables, maxTasks);
        log.info("Distributing {} table(s) across {} task(s) (tasks.max={})",
                tables.size(), groups.size(), maxTasks);

        for (List<String> group : groups) {
            Map<String, String> taskProps = new java.util.HashMap<>(configProps);
            taskProps.put(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG, String.join(",", group));
            configs.add(taskProps);
        }
        return configs;
    }

    @Override
    public void stop() {
        // No held resources at the connector (as opposed to task) level:
        // each task owns and closes its own JDBC connection.
    }

    @Override
    public ConfigDef config() {
        return IrisSourceConnectorConfig.CONFIG_DEF;
    }

    @Override
    public Config validate(Map<String, String> connectorConfigs) {
        // Delegate to the default ConfigDef-driven validation, then layer on
        // the cross-field checks (exactly-one-of table.whitelist/query, mode
        // requires the matching column names) that IrisSourceConnectorConfig's
        // constructor performs. Those throw ConfigException on construction,
        // which the default validate() machinery cannot see, so surfacing them
        // through the normal ConfigDef.validate() Config result -- rather than
        // letting the connector fail to start with a bare stack trace -- takes
        // this explicit override.
        Config config = super.validate(connectorConfigs);
        try {
            new IrisSourceConnectorConfig(connectorConfigs);
        } catch (org.apache.kafka.common.config.ConfigException e) {
            log.debug("Cross-field validation failed: {}", e.getMessage());
            // Best-effort: attach the failure to a field that's actually visible in
            // the Connect UI/REST validate response, since ConnectorUtils affords no
            // generic "form-level" error slot.
            for (var value : config.configValues()) {
                if (value.name().equals(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG)
                        || value.name().equals(IrisSourceConnectorConfig.MODE_CONFIG)) {
                    value.errorMessages().add(e.getMessage());
                }
            }
        }
        return config;
    }
}

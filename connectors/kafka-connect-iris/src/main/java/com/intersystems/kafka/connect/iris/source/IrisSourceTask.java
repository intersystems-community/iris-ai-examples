package com.intersystems.kafka.connect.iris.source;

import com.intersystems.kafka.connect.iris.Version;
import com.intersystems.kafka.connect.iris.jdbc.ConnectionFactory;
import com.intersystems.kafka.connect.iris.jdbc.DriverManagerConnectionFactory;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TimeZone;
import java.util.function.Function;
import org.apache.kafka.connect.errors.ConnectException;
import org.apache.kafka.connect.errors.RetriableException;
import org.apache.kafka.connect.source.SourceRecord;
import org.apache.kafka.connect.source.SourceTask;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Polls the tables (or the one custom query) assigned to this task and
 * emits {@link SourceRecord}s.
 *
 * <p>Offset resume works through the standard Connect mechanism: for each
 * table this task owns, {@link #start} looks up
 * {@code offsetStorageReader().offset(sourcePartitionFor(table))} and hands
 * whatever comes back (or nothing, on a table's first-ever run) to that
 * table's {@link TableQuerier}, which is what actually seeds its starting
 * position (see {@link TableQuerier} for why that seeding is
 * non-auto/explicit rather than inferred from the data).
 */
public class IrisSourceTask extends SourceTask {

    private static final Logger log = LoggerFactory.getLogger(IrisSourceTask.class);
    static final String PARTITION_TABLE_KEY = "table";

    private ConnectionFactory connectionFactory;
    private List<TableQuerier> querier;
    private String topicPrefix;
    private long pollIntervalMs;
    private boolean queryMode;
    private long lastPollStart;

    /** Test seam: lets tests inject a fake/H2 connection factory instead of DriverManager. */
    private Function<IrisSourceConnectorConfig, ConnectionFactory> connectionFactorySupplier =
            cfg -> new DriverManagerConnectionFactory(
                    cfg.getString(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG),
                    cfg.getString(IrisSourceConnectorConfig.CONNECTION_USER_CONFIG),
                    cfg.getPassword(IrisSourceConnectorConfig.CONNECTION_PASSWORD_CONFIG) == null
                            ? null
                            : cfg.getPassword(IrisSourceConnectorConfig.CONNECTION_PASSWORD_CONFIG).value());

    public IrisSourceTask() {
    }

    /** Test-only constructor: bypasses config-driven connection setup entirely. */
    IrisSourceTask(Function<IrisSourceConnectorConfig, ConnectionFactory> connectionFactorySupplier) {
        this.connectionFactorySupplier = connectionFactorySupplier;
    }

    @Override
    public String version() {
        return Version.get();
    }

    @Override
    public void start(Map<String, String> props) {
        IrisSourceConnectorConfig config = new IrisSourceConnectorConfig(props);
        this.connectionFactory = connectionFactorySupplier.apply(config);
        this.topicPrefix = config.getString(IrisSourceConnectorConfig.TOPIC_PREFIX_CONFIG);
        this.pollIntervalMs = config.getLong(IrisSourceConnectorConfig.POLL_INTERVAL_MS_CONFIG);
        this.queryMode = config.isQueryMode();

        if (queryMode) {
            String query = config.getString(IrisSourceConnectorConfig.QUERY_CONFIG);
            Map<String, Object> stored = context.offsetStorageReader().offset(sourcePartitionForQuery());
            this.querier = List.of(new TableQuerier(
                    query, config.getInt(IrisSourceConnectorConfig.BATCH_MAX_ROWS_CONFIG), stored));
        } else {
            List<String> tables = config.getList(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG);
            List<TableQuerier> built = new ArrayList<>(tables.size());
            for (String table : tables) {
                Map<String, Object> stored = context.offsetStorageReader().offset(sourcePartitionForTable(table));
                built.add(new TableQuerier(
                        table,
                        config.mode(),
                        config.getString(IrisSourceConnectorConfig.INCREMENTING_COLUMN_CONFIG),
                        config.getString(IrisSourceConnectorConfig.TIMESTAMP_COLUMN_CONFIG),
                        config.getInt(IrisSourceConnectorConfig.BATCH_MAX_ROWS_CONFIG),
                        config.getLong(IrisSourceConnectorConfig.TIMESTAMP_DELAY_MS_CONFIG),
                        TimeZone.getTimeZone(config.getString(IrisSourceConnectorConfig.DB_TIMEZONE_CONFIG)),
                        config.getLong(IrisSourceConnectorConfig.INCREMENTING_INITIAL_CONFIG),
                        config.getLong(IrisSourceConnectorConfig.TIMESTAMP_INITIAL_CONFIG),
                        stored));
            }
            this.querier = built;
        }
        log.info("Started IRIS source task with {} table(s)/queries, mode={}, topicPrefix={}",
                querier.size(), queryMode ? "query(bulk)" : "table", topicPrefix);
    }

    static Map<String, String> sourcePartitionForTable(String table) {
        return Collections.singletonMap(PARTITION_TABLE_KEY, table);
    }

    private static Map<String, String> sourcePartitionForQuery() {
        return Collections.singletonMap(PARTITION_TABLE_KEY, "__query__");
    }

    @Override
    public List<SourceRecord> poll() throws InterruptedException {
        throttle();

        Connection connection;
        try {
            connection = connectionFactory.getConnection();
        } catch (SQLException e) {
            throw new RetriableException("Failed to obtain IRIS JDBC connection", e);
        }

        List<SourceRecord> records = new ArrayList<>();
        for (TableQuerier q : querier) {
            String label = q.tableOrQueryLabel();
            Map<String, String> sourcePartition = queryMode
                    ? sourcePartitionForQuery()
                    : sourcePartitionForTable(label);
            String topic = queryMode ? topicPrefix : topicPrefix + label;

            List<TableQuerier.QueriedRow> rows;
            try {
                rows = q.poll(connection);
            } catch (SQLException e) {
                throw new ConnectException("Query failed for " + label, e);
            }

            for (TableQuerier.QueriedRow row : rows) {
                Map<String, Object> value = new LinkedHashMap<>(row.columns());
                records.add(new SourceRecord(sourcePartition, row.sourceOffset(), topic, null, value));
            }
            if (!rows.isEmpty()) {
                log.debug("Polled {} row(s) from {}", rows.size(), label);
            }
        }
        return records;
    }

    private void throttle() throws InterruptedException {
        long now = System.currentTimeMillis();
        long elapsed = now - lastPollStart;
        if (lastPollStart != 0 && elapsed < pollIntervalMs) {
            Thread.sleep(pollIntervalMs - elapsed);
        }
        lastPollStart = System.currentTimeMillis();
    }

    @Override
    public void stop() {
        if (connectionFactory != null) {
            connectionFactory.close();
        }
    }
}

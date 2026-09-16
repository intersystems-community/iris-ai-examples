package com.intersystems.kafka.connect.iris.sink;

import com.intersystems.kafka.connect.iris.Version;
import com.intersystems.kafka.connect.iris.jdbc.ConnectionFactory;
import com.intersystems.kafka.connect.iris.jdbc.DriverManagerConnectionFactory;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.apache.kafka.connect.data.Field;
import org.apache.kafka.connect.data.Struct;
import org.apache.kafka.connect.errors.ConnectException;
import org.apache.kafka.connect.errors.RetriableException;
import org.apache.kafka.connect.sink.SinkRecord;
import org.apache.kafka.connect.sink.SinkTask;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Writes records to IRIS tables with batching, upsert support, retry on
 * transient failure, and a dead-letter path for records that are
 * individually bad (not a connectivity problem -- a row IRIS itself
 * rejects, e.g. on a type or constraint violation).
 *
 * <p>The retry/dead-letter split is deliberate:
 * <ul>
 *   <li>A {@link SQLException} thrown while writing an individual row is
 *       treated as that row being bad. It is not retried (retrying a
 *       constraint violation just fails the same way again) -- it goes
 *       straight to {@link DeadLetterHandler}.</li>
 *   <li>A {@link SQLException} thrown obtaining the connection itself, or
 *       failing to commit, is treated as transient/connectivity. The whole
 *       chunk is retried up to {@code max.retries} times with
 *       {@code retry.backoff.ms} between attempts before every record in
 *       it is dead-lettered.</li>
 * </ul>
 */
public class IrisSinkTask extends SinkTask {

    private static final Logger log = LoggerFactory.getLogger(IrisSinkTask.class);

    private ConnectionFactory connectionFactory;
    private IrisTableWriter writer;
    private DeadLetterHandler deadLetterHandler;
    private String tableNameFormat;
    private int batchSize;
    private int maxRetries;
    private long retryBackoffMs;

    private Function<IrisSinkConnectorConfig, ConnectionFactory> connectionFactorySupplier =
            cfg -> new DriverManagerConnectionFactory(
                    cfg.getString(IrisSinkConnectorConfig.CONNECTION_URL_CONFIG),
                    cfg.getString(IrisSinkConnectorConfig.CONNECTION_USER_CONFIG),
                    cfg.getPassword(IrisSinkConnectorConfig.CONNECTION_PASSWORD_CONFIG) == null
                            ? null
                            : cfg.getPassword(IrisSinkConnectorConfig.CONNECTION_PASSWORD_CONFIG).value());

    public IrisSinkTask() {
    }

    /** Test-only constructor: bypasses config-driven connection setup entirely. */
    IrisSinkTask(Function<IrisSinkConnectorConfig, ConnectionFactory> connectionFactorySupplier) {
        this.connectionFactorySupplier = connectionFactorySupplier;
    }

    @Override
    public String version() {
        return Version.get();
    }

    @Override
    public void start(Map<String, String> props) {
        IrisSinkConnectorConfig config = new IrisSinkConnectorConfig(props);
        this.connectionFactory = connectionFactorySupplier.apply(config);
        this.writer = new IrisTableWriter(config.insertMode(), config.getList(IrisSinkConnectorConfig.PK_FIELDS_CONFIG));
        this.deadLetterHandler = new DeadLetterHandler(safeErrantRecordReporter());
        this.tableNameFormat = config.getString(IrisSinkConnectorConfig.TABLE_NAME_FORMAT_CONFIG);
        this.batchSize = config.getInt(IrisSinkConnectorConfig.BATCH_SIZE_CONFIG);
        this.maxRetries = config.getInt(IrisSinkConnectorConfig.MAX_RETRIES_CONFIG);
        this.retryBackoffMs = config.getLong(IrisSinkConnectorConfig.RETRY_BACKOFF_MS_CONFIG);
        log.info("Started IRIS sink task: insertMode={}, tableNameFormat={}, batchSize={}",
                config.insertMode(), tableNameFormat, batchSize);
    }

    /** {@code context.errantRecordReporter()} throws on Connect runtimes older than 2.6; treat that as "none available". */
    private org.apache.kafka.connect.sink.ErrantRecordReporter safeErrantRecordReporter() {
        try {
            return context.errantRecordReporter();
        } catch (NoSuchMethodError | UnsupportedOperationException e) {
            log.warn("ErrantRecordReporter not available on this Connect runtime; "
                    + "dead-lettered records will only be logged.", e);
            return null;
        }
    }

    @Override
    public void put(Collection<SinkRecord> records) {
        if (records.isEmpty()) {
            return;
        }

        // Group by destination table, preserving per-topic record order within each group.
        Map<String, List<SinkRecord>> byTable = new LinkedHashMap<>();
        for (SinkRecord record : records) {
            String table = IrisTableWriter.resolveTableName(tableNameFormat, record.topic());
            byTable.computeIfAbsent(table, t -> new ArrayList<>()).add(record);
        }

        for (Map.Entry<String, List<SinkRecord>> entry : byTable.entrySet()) {
            for (List<SinkRecord> chunk : chunk(entry.getValue(), batchSize)) {
                writeChunkWithRetry(entry.getKey(), chunk);
            }
        }
    }

    private static <T> List<List<T>> chunk(List<T> items, int size) {
        List<List<T>> chunks = new ArrayList<>();
        for (int i = 0; i < items.size(); i += size) {
            chunks.add(items.subList(i, Math.min(i + size, items.size())));
        }
        return chunks;
    }

    private void writeChunkWithRetry(String table, List<SinkRecord> chunk) {
        int attempt = 0;
        while (true) {
            try {
                writeChunk(table, chunk);
                return;
            } catch (SQLException connectivityFailure) {
                attempt++;
                if (attempt > maxRetries) {
                    log.error("Giving up on {} record(s) for table {} after {} attempt(s)",
                            chunk.size(), table, attempt, connectivityFailure);
                    for (SinkRecord record : chunk) {
                        deadLetterHandler.deadLetter(record, connectivityFailure);
                    }
                    return;
                }
                log.warn("Write to {} failed (attempt {}/{}), retrying in {} ms: {}",
                        table, attempt, maxRetries, retryBackoffMs, connectivityFailure.getMessage());
                sleep(retryBackoffMs);
            }
        }
    }

    /**
     * Writes one chunk in one transaction. A {@link SQLException} thrown here
     * (connection/commit failure) propagates to the caller for retry; a
     * per-row write failure is caught individually and the offending record
     * is dead-lettered without failing the rest of the chunk.
     */
    private void writeChunk(String table, List<SinkRecord> chunk) throws SQLException {
        Connection connection = connectionFactory.getConnection();
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);
        try {
            for (SinkRecord record : chunk) {
                try {
                    writer.writeRecord(connection, table, valueAsFieldMap(record));
                } catch (SQLException rowFailure) {
                    log.warn("Row failed to write to {} (topic={}, offset={}); dead-lettering: {}",
                            table, record.topic(), record.kafkaOffset(), rowFailure.getMessage());
                    deadLetterHandler.deadLetter(record, rowFailure);
                }
            }
            connection.commit();
        } catch (SQLException commitFailure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                log.warn("Rollback also failed for table {}", table, rollbackFailure);
            }
            throw commitFailure;
        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }

    /** Accepts either schemaless (Map) or schema'd (Struct) record values. */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> valueAsFieldMap(SinkRecord record) {
        Object value = record.value();
        if (value instanceof Map<?, ?> map) {
            return IrisTableWriter.orderedCopy((Map<String, Object>) map);
        }
        if (value instanceof Struct struct) {
            Map<String, Object> fields = new LinkedHashMap<>();
            for (Field field : struct.schema().fields()) {
                fields.put(field.name(), struct.get(field));
            }
            return fields;
        }
        throw new ConnectException("Unsupported record value type for topic " + record.topic() + ": "
                + (value == null ? "null" : value.getClass().getName())
                + ". Expected a schemaless Map or a Struct.");
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RetriableException("Interrupted during retry backoff", e);
        }
    }

    @Override
    public void stop() {
        if (connectionFactory != null) {
            connectionFactory.close();
        }
    }
}

package com.intersystems.kafka.connect.iris.sink;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.intersystems.kafka.connect.iris.jdbc.ConnectionFactory;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.kafka.connect.data.Schema;
import org.apache.kafka.connect.data.SchemaBuilder;
import org.apache.kafka.connect.data.Struct;
import org.apache.kafka.connect.sink.ErrantRecordReporter;
import org.apache.kafka.connect.sink.SinkRecord;
import org.apache.kafka.connect.sink.SinkTaskContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * Batching, upsert, connection-retry, and dead-letter behavior of
 * {@link IrisSinkTask}, using H2 as the JDBC backend (STAND-IN FOR IRIS,
 * NOT IRIS -- see {@code source/TableQuerierH2Test}'s javadoc for the
 * general caveat) and Mockito for the Connect-framework pieces
 * ({@link SinkTaskContext}, {@link ErrantRecordReporter}) a task never
 * constructs itself.
 */
@ExtendWith(MockitoExtension.class)
class IrisSinkTaskH2Test {

    private static final AtomicInteger DB_COUNTER = new AtomicInteger();
    private String jdbcUrl;
    private Connection setupConnection;

    @BeforeEach
    void setUp() throws SQLException {
        jdbcUrl = "jdbc:h2:mem:sinktask" + DB_COUNTER.incrementAndGet() + ";DB_CLOSE_DELAY=-1";
        setupConnection = DriverManager.getConnection(jdbcUrl);
        try (Statement stmt = setupConnection.createStatement()) {
            stmt.execute("CREATE TABLE Patient (id BIGINT PRIMARY KEY, name VARCHAR(100))");
        }
    }

    @AfterEach
    void tearDown() throws SQLException {
        setupConnection.close();
    }

    private Map<String, String> baseProps() {
        Map<String, String> props = new HashMap<>();
        props.put(IrisSinkConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:IRIS://placeholder:1972/USER");
        props.put(IrisSinkConnectorConfig.TABLE_NAME_FORMAT_CONFIG, "${topic}");
        props.put(IrisSinkConnectorConfig.PK_FIELDS_CONFIG, "ID");
        props.put(IrisSinkConnectorConfig.INSERT_MODE_CONFIG, "upsert");
        props.put(IrisSinkConnectorConfig.BATCH_SIZE_CONFIG, "2");
        props.put(IrisSinkConnectorConfig.MAX_RETRIES_CONFIG, "2");
        props.put(IrisSinkConnectorConfig.RETRY_BACKOFF_MS_CONFIG, "1");
        return props;
    }

    private SinkRecord schemalessRecord(long offset, long id, String name) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("ID", id);
        value.put("NAME", name);
        return new SinkRecord("Patient", 0, null, null, null, value, offset);
    }

    private int countRows() throws SQLException {
        try (Statement stmt = setupConnection.createStatement();
                ResultSet rs = stmt.executeQuery("SELECT COUNT(*) FROM Patient")) {
            rs.next();
            return rs.getInt(1);
        }
    }

    /** Test ConnectionFactory: a real H2 connection, but can be made to fail N times before succeeding. */
    private static class FlakyH2ConnectionFactory implements ConnectionFactory {
        private final String url;
        private final int failuresBeforeSuccess;
        private int attempts = 0;
        private Connection conn;

        FlakyH2ConnectionFactory(String url, int failuresBeforeSuccess) {
            this.url = url;
            this.failuresBeforeSuccess = failuresBeforeSuccess;
        }

        @Override
        public Connection getConnection() throws SQLException {
            attempts++;
            if (attempts <= failuresBeforeSuccess) {
                throw new SQLException("simulated connection failure #" + attempts);
            }
            if (conn == null || conn.isClosed()) {
                conn = DriverManager.getConnection(url);
            }
            return conn;
        }

        @Override
        public boolean isClosed() throws SQLException {
            return conn == null || conn.isClosed();
        }

        @Override
        public void close() {
            try {
                if (conn != null) {
                    conn.close();
                }
            } catch (SQLException e) {
                throw new RuntimeException(e);
            }
        }
    }

    @Test
    void putWritesAllRecordsAcrossMultipleBatches() throws SQLException, InterruptedException {
        SinkTaskContext context = mock(SinkTaskContext.class);
        when(context.errantRecordReporter()).thenReturn(mock(ErrantRecordReporter.class));

        IrisSinkTask task = new IrisSinkTask(cfg -> new FlakyH2ConnectionFactory(jdbcUrl, 0));
        task.initialize(context);
        task.start(baseProps()); // batch.size=2

        List<SinkRecord> records = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            records.add(schemalessRecord(i, i, "Patient" + i));
        }
        task.put(records);

        assertEquals(5, countRows(), "all 5 records should land despite batch.size=2 splitting them into 3 batches");
        task.stop();
    }

    @Test
    void upsertModeUpdatesExistingRowsAcrossSeparatePutCalls() throws SQLException {
        SinkTaskContext context = mock(SinkTaskContext.class);
        when(context.errantRecordReporter()).thenReturn(mock(ErrantRecordReporter.class));

        IrisSinkTask task = new IrisSinkTask(cfg -> new FlakyH2ConnectionFactory(jdbcUrl, 0));
        task.initialize(context);
        task.start(baseProps());

        task.put(List.of(schemalessRecord(0, 1, "Alice")));
        task.put(List.of(schemalessRecord(1, 1, "Alice Updated")));

        assertEquals(1, countRows(), "second put should update, not duplicate, id=1");
        task.stop();
    }

    @Test
    void structValuedRecordsAreAccepted() throws SQLException {
        SinkTaskContext context = mock(SinkTaskContext.class);
        when(context.errantRecordReporter()).thenReturn(mock(ErrantRecordReporter.class));

        IrisSinkTask task = new IrisSinkTask(cfg -> new FlakyH2ConnectionFactory(jdbcUrl, 0));
        task.initialize(context);
        task.start(baseProps());

        Schema schema = SchemaBuilder.struct().field("ID", Schema.INT64_SCHEMA).field("NAME", Schema.STRING_SCHEMA)
                .build();
        Struct value = new Struct(schema).put("ID", 42L).put("NAME", "StructPatient");
        SinkRecord record = new SinkRecord("Patient", 0, null, null, schema, value, 0);

        task.put(List.of(record));

        assertEquals(1, countRows());
        task.stop();
    }

    @Test
    void aBadRowIsDeadLetteredWithoutFailingTheRestOfTheBatch() throws SQLException {
        SinkTaskContext context = mock(SinkTaskContext.class);
        ErrantRecordReporter reporter = mock(ErrantRecordReporter.class);
        when(context.errantRecordReporter()).thenReturn(reporter);

        IrisSinkTask task = new IrisSinkTask(cfg -> new FlakyH2ConnectionFactory(jdbcUrl, 0));
        task.initialize(context);
        Map<String, String> props = baseProps();
        props.put(IrisSinkConnectorConfig.INSERT_MODE_CONFIG, "insert");
        props.put(IrisSinkConnectorConfig.BATCH_SIZE_CONFIG, "10");
        task.start(props);

        SinkRecord good1 = schemalessRecord(0, 1, "Alice");
        SinkRecord duplicate = schemalessRecord(1, 1, "DuplicatePk"); // same PK -> constraint violation under INSERT
        SinkRecord good2 = schemalessRecord(2, 2, "Bob");
        task.put(List.of(good1, duplicate, good2));

        assertEquals(2, countRows(), "the two good rows should still be written");
        ArgumentCaptor<Throwable> causeCaptor = ArgumentCaptor.forClass(Throwable.class);
        verify(reporter, times(1)).report(org.mockito.ArgumentMatchers.eq(duplicate), causeCaptor.capture());
        assertTrue(causeCaptor.getValue() instanceof SQLException);

        task.stop();
    }

    @Test
    void aConnectivityFailureIsRetriedThenSucceeds() throws SQLException {
        SinkTaskContext context = mock(SinkTaskContext.class);
        when(context.errantRecordReporter()).thenReturn(mock(ErrantRecordReporter.class));

        // Fails the first 2 getConnection() calls, succeeds on the 3rd. max.retries=2 in baseProps
        // means attempt 1 (fails), retry 1 (fails), retry 2 (succeeds) -- exactly at the limit.
        IrisSinkTask task = new IrisSinkTask(cfg -> new FlakyH2ConnectionFactory(jdbcUrl, 2));
        task.initialize(context);
        task.start(baseProps());

        task.put(List.of(schemalessRecord(0, 1, "Alice")));

        assertEquals(1, countRows(), "should succeed once retries exhaust the simulated outage");
        task.stop();
    }

    @Test
    void exhaustingAllRetriesDeadLettersTheWholeChunk() throws SQLException {
        SinkTaskContext context = mock(SinkTaskContext.class);
        ErrantRecordReporter reporter = mock(ErrantRecordReporter.class);
        when(context.errantRecordReporter()).thenReturn(reporter);

        // Fails every attempt (1 initial + 2 retries = 3 total, but this factory never recovers).
        IrisSinkTask task = new IrisSinkTask(cfg -> new FlakyH2ConnectionFactory(jdbcUrl, Integer.MAX_VALUE));
        task.initialize(context);
        task.start(baseProps());

        SinkRecord record = schemalessRecord(0, 1, "Alice");
        task.put(List.of(record));

        assertEquals(0, countRows());
        verify(reporter, times(1)).report(org.mockito.ArgumentMatchers.eq(record), org.mockito.ArgumentMatchers.any());
        task.stop();
    }
}

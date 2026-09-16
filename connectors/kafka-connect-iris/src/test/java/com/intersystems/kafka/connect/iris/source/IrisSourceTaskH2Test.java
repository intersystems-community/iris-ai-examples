package com.intersystems.kafka.connect.iris.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.intersystems.kafka.connect.iris.jdbc.ConnectionFactory;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.kafka.connect.source.SourceRecord;
import org.apache.kafka.connect.source.SourceTaskContext;
import org.apache.kafka.connect.storage.OffsetStorageReader;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * End-to-end (within this task) test of {@link IrisSourceTask}: config ->
 * offset-storage lookup -> polling -> {@link SourceRecord} shape, using H2
 * as the JDBC backend (STAND-IN FOR IRIS, NOT IRIS -- see
 * {@link TableQuerierH2Test}'s javadoc for the caveat this inherits) and
 * Mockito to stand in for the parts of the Connect framework
 * ({@link SourceTaskContext}, {@link OffsetStorageReader}) that a task
 * never constructs itself.
 */
@ExtendWith(MockitoExtension.class)
class IrisSourceTaskH2Test {

    private static final AtomicInteger DB_COUNTER = new AtomicInteger();
    private String jdbcUrl;
    private Connection setupConnection;

    @BeforeEach
    void setUp() throws SQLException {
        jdbcUrl = "jdbc:h2:mem:sourcetask" + DB_COUNTER.incrementAndGet() + ";DB_CLOSE_DELAY=-1";
        setupConnection = DriverManager.getConnection(jdbcUrl);
        try (Statement stmt = setupConnection.createStatement()) {
            stmt.execute("CREATE TABLE Patient (id BIGINT PRIMARY KEY, name VARCHAR(100))");
            stmt.execute("INSERT INTO Patient (id, name) VALUES (1, 'Alice')");
            stmt.execute("INSERT INTO Patient (id, name) VALUES (2, 'Bob')");
        }
    }

    @AfterEach
    void tearDown() throws SQLException {
        setupConnection.close();
    }

    private Map<String, String> baseProps() {
        Map<String, String> props = new HashMap<>();
        props.put(IrisSourceConnectorConfig.CONNECTION_URL_CONFIG, "jdbc:IRIS://placeholder:1972/USER");
        props.put(IrisSourceConnectorConfig.TOPIC_PREFIX_CONFIG, "iris.");
        props.put(IrisSourceConnectorConfig.TABLE_WHITELIST_CONFIG, "Patient");
        props.put(IrisSourceConnectorConfig.MODE_CONFIG, "incrementing");
        props.put(IrisSourceConnectorConfig.INCREMENTING_COLUMN_CONFIG, "id");
        return props;
    }

    /** A ConnectionFactory seam impl that just hands back a real (H2) JDBC connection. */
    private ConnectionFactory h2ConnectionFactory() {
        return new ConnectionFactory() {
            private Connection conn;

            @Override
            public Connection getConnection() throws SQLException {
                if (conn == null || conn.isClosed()) {
                    conn = DriverManager.getConnection(jdbcUrl);
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
        };
    }

    @Test
    void pollEmitsOneSourceRecordPerRowWithTablePartitionAndPrefixedTopic() throws InterruptedException {
        SourceTaskContext context = mock(SourceTaskContext.class);
        OffsetStorageReader offsetReader = mock(OffsetStorageReader.class);
        when(context.offsetStorageReader()).thenReturn(offsetReader);
        doReturn(null).when(offsetReader).offset(any(Map.class));

        IrisSourceTask task = new IrisSourceTask(cfg -> h2ConnectionFactory());
        task.initialize(context);
        task.start(baseProps());

        List<SourceRecord> records = task.poll();

        assertEquals(2, records.size());
        SourceRecord first = records.get(0);
        assertEquals("iris.Patient", first.topic());
        assertEquals(Map.of(IrisSourceTask.PARTITION_TABLE_KEY, "Patient"), first.sourcePartition());
        assertEquals(Map.of(TableQuerier.OFFSET_INCREMENTING, 1L), first.sourceOffset());

        task.stop();
    }

    @Test
    void pollResumesFromAPreviouslyCommittedOffset() throws InterruptedException {
        SourceTaskContext context = mock(SourceTaskContext.class);
        OffsetStorageReader offsetReader = mock(OffsetStorageReader.class);
        when(context.offsetStorageReader()).thenReturn(offsetReader);
        // Simulate a restart where Connect's offset storage already has id=1 committed.
        doReturn(Map.of(TableQuerier.OFFSET_INCREMENTING, 1L)).when(offsetReader).offset(any(Map.class));

        IrisSourceTask task = new IrisSourceTask(cfg -> h2ConnectionFactory());
        task.initialize(context);
        task.start(baseProps());

        List<SourceRecord> records = task.poll();

        assertEquals(1, records.size(), "should resume after id=1, not replay it");
        assertEquals(2L, ((Map<?, ?>) records.get(0).value()).get("ID"));

        task.stop();
    }

    @Test
    void secondPollWithNothingNewReturnsAnEmptyList() throws InterruptedException, SQLException {
        SourceTaskContext context = mock(SourceTaskContext.class);
        OffsetStorageReader offsetReader = mock(OffsetStorageReader.class);
        when(context.offsetStorageReader()).thenReturn(offsetReader);
        doReturn(null).when(offsetReader).offset(any(Map.class));

        Map<String, String> props = baseProps();
        props.put(IrisSourceConnectorConfig.POLL_INTERVAL_MS_CONFIG, "1");
        IrisSourceTask task = new IrisSourceTask(cfg -> h2ConnectionFactory());
        task.initialize(context);
        task.start(props);

        assertEquals(2, task.poll().size());
        assertTrue(task.poll().isEmpty());

        task.stop();
    }
}

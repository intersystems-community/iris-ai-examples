package com.intersystems.kafka.connect.iris.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import java.util.TimeZone;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Exercises {@link TableQuerier}'s SQL generation and offset tracking
 * against H2.
 *
 * <p><b>H2 is a STAND-IN FOR IRIS, NOT IRIS.</b> It is an in-memory
 * ANSI-SQL database used here only because there is no live IRIS instance
 * in this environment. Its SQL dialect, its transaction/locking model, and
 * its column type mapping (particularly for TIMESTAMP precision and for
 * IRIS-specific types) differ from IRIS's in ways this suite cannot catch.
 * What passing here proves is that {@code TableQuerier}'s Java logic --
 * query construction, parameter binding, offset advancement, resume from a
 * stored offset -- behaves as designed against a real JDBC ResultSet. It
 * does NOT prove IRIS compatibility. See STATUS.md.
 */
class TableQuerierH2Test {

    private static final AtomicInteger DB_COUNTER = new AtomicInteger();
    private Connection connection;

    @BeforeEach
    void setUp() throws SQLException {
        // A fresh named in-memory DB per test avoids any cross-test state bleed.
        connection = DriverManager.getConnection(
                "jdbc:h2:mem:tablequerier" + DB_COUNTER.incrementAndGet() + ";DB_CLOSE_DELAY=-1");
        try (Statement stmt = connection.createStatement()) {
            stmt.execute("CREATE TABLE Patient (id BIGINT PRIMARY KEY, name VARCHAR(100), updated_at TIMESTAMP)");
        }
    }

    @AfterEach
    void tearDown() throws SQLException {
        connection.close();
    }

    private void insertPatient(long id, String name, long epochMillis) throws SQLException {
        try (var stmt = connection.prepareStatement(
                "INSERT INTO Patient (id, name, updated_at) VALUES (?, ?, ?)")) {
            stmt.setLong(1, id);
            stmt.setString(2, name);
            stmt.setTimestamp(3, new java.sql.Timestamp(epochMillis));
            stmt.executeUpdate();
        }
    }

    // ---- bulk mode ----

    @Test
    void bulkModeAlwaysReadsEveryRow() throws SQLException {
        insertPatient(1, "Alice", 1000L);
        insertPatient(2, "Bob", 2000L);

        TableQuerier querier = new TableQuerier("Patient", QueryMode.BULK, null, null, 100, 0,
                TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> first = querier.poll(connection);
        assertEquals(2, first.size());

        insertPatient(3, "Carol", 3000L);
        List<TableQuerier.QueriedRow> second = querier.poll(connection);
        assertEquals(3, second.size(), "bulk mode re-reads the whole table every poll");
    }

    @Test
    void bulkModeHonorsBatchMaxRows() throws SQLException {
        for (int i = 0; i < 10; i++) {
            insertPatient(i, "Patient" + i, 1000L + i);
        }
        TableQuerier querier = new TableQuerier("Patient", QueryMode.BULK, null, null, 3, 0,
                TimeZone.getTimeZone("UTC"), -1, -1, null);
        assertEquals(3, querier.poll(connection).size());
    }

    // ---- incrementing mode ----

    @Test
    void incrementingModeOnlyReturnsRowsPastTheLastOffset() throws SQLException {
        insertPatient(1, "Alice", 1000L);
        insertPatient(2, "Bob", 2000L);

        TableQuerier querier = new TableQuerier("Patient", QueryMode.INCREMENTING, "id", null, 100, 0,
                TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> first = querier.poll(connection);
        assertEquals(2, first.size());
        assertEquals(2L, querier.lastIncrementing());

        // Nothing new yet: second poll should come back empty.
        assertEquals(0, querier.poll(connection).size());

        insertPatient(3, "Carol", 3000L);
        List<TableQuerier.QueriedRow> third = querier.poll(connection);
        assertEquals(1, third.size());
        assertEquals(3L, (Long) third.get(0).columns().get("ID"));
    }

    @Test
    void incrementingModeResumesFromAStoredOffsetAfterRestart() throws SQLException {
        insertPatient(1, "Alice", 1000L);
        insertPatient(2, "Bob", 2000L);
        insertPatient(3, "Carol", 3000L);

        // Simulate a task restart: a brand new TableQuerier, seeded only from
        // what Kafka Connect's offset storage would have returned -- not from
        // any in-memory state, and not from re-deriving a starting point by
        // querying the table.
        Map<String, Object> storedOffset = Map.of(TableQuerier.OFFSET_INCREMENTING, 1L);
        TableQuerier resumed = new TableQuerier("Patient", QueryMode.INCREMENTING, "id", null, 100, 0,
                TimeZone.getTimeZone("UTC"), -1, -1, storedOffset);

        List<TableQuerier.QueriedRow> rows = resumed.poll(connection);
        assertEquals(2, rows.size(), "should resume after id=1, re-reading ids 2 and 3 only");
    }

    @Test
    void incrementingModeWithNoStoredOffsetUsesTheConfiguredNonAutoInitialValue() throws SQLException {
        insertPatient(1, "Alice", 1000L);
        insertPatient(2, "Bob", 2000L);
        insertPatient(3, "Carol", 3000L);

        // No stored offset (first-ever run) and an operator-pinned initial
        // offset of 2 -- this is the non-auto offset handling the connector
        // exists to provide: the starting point is a config value, not
        // something the connector inferred from MIN()/MAX() on the table.
        TableQuerier querier = new TableQuerier("Patient", QueryMode.INCREMENTING, "id", null, 100, 0,
                TimeZone.getTimeZone("UTC"), 2, -1, null);

        List<TableQuerier.QueriedRow> rows = querier.poll(connection);
        assertEquals(1, rows.size());
        assertEquals(3L, (Long) rows.get(0).columns().get("ID"));
    }

    // ---- timestamp mode ----

    @Test
    void timestampModeOnlyReturnsRowsNewerThanTheLastOffset() throws SQLException {
        long now = System.currentTimeMillis();
        insertPatient(1, "Alice", now - 10_000);
        insertPatient(2, "Bob", now - 5_000);

        TableQuerier querier = new TableQuerier("Patient", QueryMode.TIMESTAMP, null, "updated_at", 100, 0,
                TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> first = querier.poll(connection);
        assertEquals(2, first.size());

        // Nothing new since the last poll's high-water mark: an immediate
        // second poll should come back empty.
        assertEquals(0, querier.poll(connection).size());
    }

    @Test
    void timestampModeExcludesRowsTimestampedBeyondTheQuerysUpperBound() throws SQLException {
        long now = System.currentTimeMillis();
        insertPatient(1, "Alice", now - 10_000);
        // Timestamped well into the future -- the upper bound (effectively
        // "now" at query time) has not reached it yet.
        insertPatient(2, "FutureRow", now + 3_600_000);

        TableQuerier querier = new TableQuerier("Patient", QueryMode.TIMESTAMP, null, "updated_at", 100, 0,
                TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> rows = querier.poll(connection);
        assertEquals(1, rows.size(), "a row timestamped in the future must not be emitted early");
        assertEquals("Alice", rows.get(0).columns().get("NAME"));
    }

    @Test
    void timestampDelayExcludesRowsInsideTheDelayWindowButKeepsOlderOnes() throws SQLException {
        long now = System.currentTimeMillis();
        // Older than the 5s delay window: upper bound (now - 5000) is at or
        // past this row's timestamp, so it must be included.
        insertPatient(1, "OldEnough", now - 10_000);
        // Inside the delay window: upper bound (now - 5000) has not reached
        // this row's timestamp yet, so it must be held back this poll -- the
        // guard against reading a row before every row that could still
        // arrive with an earlier-but-not-yet-visible timestamp has settled.
        insertPatient(2, "TooRecent", now - 1_000);

        TableQuerier querier = new TableQuerier("Patient", QueryMode.TIMESTAMP, null, "updated_at", 100, 5_000,
                TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> rows = querier.poll(connection);
        assertEquals(1, rows.size(), "only the row older than the delay window should be returned");
        assertEquals("OldEnough", rows.get(0).columns().get("NAME"));
    }

    // ---- timestamp+incrementing mode ----

    @Test
    void timestampIncrementingBreaksTiesWithinTheSameTimestampByIncrementingColumn() throws SQLException {
        long ts = System.currentTimeMillis() - 60_000;
        // Three rows sharing exactly the same timestamp -- the scenario
        // plain timestamp-mode cannot order safely, which is the whole
        // reason this mode exists.
        insertPatient(1, "Alice", ts);
        insertPatient(2, "Bob", ts);
        insertPatient(3, "Carol", ts);

        TableQuerier querier = new TableQuerier("Patient", QueryMode.TIMESTAMP_INCREMENTING, "id", "updated_at",
                2, 0, TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> first = querier.poll(connection);
        assertEquals(2, first.size(), "batch.max.rows should still cap the page size");
        assertEquals(1L, (Long) first.get(0).columns().get("ID"));
        assertEquals(2L, (Long) first.get(1).columns().get("ID"));

        List<TableQuerier.QueriedRow> second = querier.poll(connection);
        assertEquals(1, second.size(), "should pick up the remaining tied row without re-sending the first two");
        assertEquals(3L, (Long) second.get(0).columns().get("ID"));
    }

    @Test
    void timestampIncrementingAdvancesPastAnEarlierBucketsHighIncrementingValue() throws SQLException {
        long ts1 = System.currentTimeMillis() - 60_000;
        long ts2 = ts1 + 10_000;
        insertPatient(9, "LateInFirstBucket", ts1);
        insertPatient(1, "EarlyInSecondBucket", ts2); // lower id than the previous bucket's max

        // batch.max.rows=1 forces the two rows into separate polls, which is
        // what actually exercises the bug this test guards against: after
        // the first poll leaves lastIncrementing=9 (from bucket ts1), a naive
        // "incr > lastIncrementing" filter carried into the ts2 bucket would
        // wrongly skip id=1 forever.
        TableQuerier querier = new TableQuerier("Patient", QueryMode.TIMESTAMP_INCREMENTING, "id", "updated_at",
                1, 0, TimeZone.getTimeZone("UTC"), -1, -1, null);

        List<TableQuerier.QueriedRow> first = querier.poll(connection);
        assertEquals(1, first.size());
        assertEquals(9L, (Long) first.get(0).columns().get("ID"));

        List<TableQuerier.QueriedRow> second = querier.poll(connection);
        assertEquals(1, second.size(),
                "a lower incrementing value in a strictly later timestamp bucket must not be skipped");
        assertEquals(1L, (Long) second.get(0).columns().get("ID"));
    }
}

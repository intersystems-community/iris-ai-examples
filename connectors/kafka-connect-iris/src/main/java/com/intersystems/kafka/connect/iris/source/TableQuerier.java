package com.intersystems.kafka.connect.iris.source;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TimeZone;

/**
 * Builds and runs the SQL for exactly one table (or, in bulk mode, one
 * custom query) and tracks the offset state needed to resume where the
 * last poll left off.
 *
 * <p>One {@code TableQuerier} is created per table assigned to a task (see
 * {@link TaskPartitioner}) and lives for the task's lifetime, so the
 * in-memory {@code lastIncrementing}/{@code lastTimestampMillis} fields
 * persist across polls within a task run. They are seeded once, at
 * construction, from whatever Kafka Connect's offset storage returns for
 * that table (or from the configured initial-offset fallback if this is
 * the table's first-ever run) -- never re-derived from the database, which
 * is what makes offset handling here "non-auto": the starting point for a
 * never-before-seen table is a config value an operator set, not a value
 * the connector inferred by querying MIN()/MAX() on the table.
 *
 * <p>Query mode (a single arbitrary user SELECT instead of a table name)
 * is restricted to bulk polling only -- see
 * {@link IrisSourceConnectorConfig}. Splicing a WHERE/ORDER BY/LIMIT onto
 * an arbitrary caller-supplied query safely is a materially harder problem
 * (subqueries, CTEs, existing ORDER BY) than this connector takes on.
 */
public class TableQuerier {

    static final String OFFSET_INCREMENTING = "incrementing";
    static final String OFFSET_TIMESTAMP = "timestamp";
    static final String OFFSET_BULK_RUN = "bulk_run";

    private final String table;
    private final String customQuery;
    private final QueryMode mode;
    private final String incrementingColumn;
    private final String timestampColumn;
    private final int batchMaxRows;
    private final long timestampDelayMs;
    private final TimeZone dbTimeZone;

    private long lastIncrementing;
    private long lastTimestampMillis;
    private long bulkRun;

    /** Table-mode constructor. */
    public TableQuerier(String table, QueryMode mode, String incrementingColumn, String timestampColumn,
            int batchMaxRows, long timestampDelayMs, TimeZone dbTimeZone,
            long incrementingInitial, long timestampInitial, Map<String, Object> storedOffset) {
        this.table = table;
        this.customQuery = null;
        this.mode = mode;
        this.incrementingColumn = incrementingColumn;
        this.timestampColumn = timestampColumn;
        this.batchMaxRows = batchMaxRows;
        this.timestampDelayMs = timestampDelayMs;
        this.dbTimeZone = dbTimeZone;
        seedOffsets(incrementingInitial, timestampInitial, storedOffset);
    }

    /** Query-mode (bulk-only) constructor. */
    public TableQuerier(String customQuery, int batchMaxRows, Map<String, Object> storedOffset) {
        this.table = null;
        this.customQuery = customQuery;
        this.mode = QueryMode.BULK;
        this.incrementingColumn = null;
        this.timestampColumn = null;
        this.batchMaxRows = batchMaxRows;
        this.timestampDelayMs = 0;
        this.dbTimeZone = TimeZone.getTimeZone("UTC");
        seedOffsets(-1, -1, storedOffset);
    }

    private void seedOffsets(long incrementingInitial, long timestampInitial, Map<String, Object> storedOffset) {
        if (storedOffset != null && storedOffset.get(OFFSET_INCREMENTING) instanceof Number n) {
            this.lastIncrementing = n.longValue();
        } else {
            this.lastIncrementing = incrementingInitial;
        }
        if (storedOffset != null && storedOffset.get(OFFSET_TIMESTAMP) instanceof Number n) {
            this.lastTimestampMillis = n.longValue();
        } else {
            this.lastTimestampMillis = timestampInitial;
        }
        if (storedOffset != null && storedOffset.get(OFFSET_BULK_RUN) instanceof Number n) {
            this.bulkRun = n.longValue();
        } else {
            this.bulkRun = 0;
        }
    }

    public String tableOrQueryLabel() {
        return table != null ? table : customQuery;
    }

    /** Result of one poll: the rows fetched, each paired with the source offset to record for it. */
    public record QueriedRow(Map<String, Object> columns, Map<String, Object> sourceOffset) {
    }

    public List<QueriedRow> poll(Connection connection) throws SQLException {
        String sql = buildQuery();
        try (PreparedStatement stmt = connection.prepareStatement(sql)) {
            bindParams(stmt);
            try (ResultSet rs = stmt.executeQuery()) {
                return extractAndAdvance(rs);
            }
        }
    }

    String buildQuery() {
        if (customQuery != null) {
            // Bulk-only, per the class javadoc; batch.max.rows is still honored so
            // one poll cannot pull an unbounded custom-query result set.
            return customQuery + " LIMIT " + batchMaxRows;
        }
        return switch (mode) {
            case BULK -> "SELECT * FROM " + table + " LIMIT " + batchMaxRows;
            case INCREMENTING -> "SELECT * FROM " + table
                    + " WHERE " + incrementingColumn + " > ?"
                    + " ORDER BY " + incrementingColumn + " ASC"
                    + " LIMIT " + batchMaxRows;
            case TIMESTAMP -> "SELECT * FROM " + table
                    + " WHERE " + timestampColumn + " > ? AND " + timestampColumn + " <= ?"
                    + " ORDER BY " + timestampColumn + " ASC"
                    + " LIMIT " + batchMaxRows;
            case TIMESTAMP_INCREMENTING -> "SELECT * FROM " + table
                    + " WHERE (" + timestampColumn + " = ? AND " + incrementingColumn + " > ?)"
                    + " OR " + timestampColumn + " > ?"
                    + " AND " + timestampColumn + " <= ?"
                    + " ORDER BY " + timestampColumn + " ASC, " + incrementingColumn + " ASC"
                    + " LIMIT " + batchMaxRows;
        };
    }

    private void bindParams(PreparedStatement stmt) throws SQLException {
        Calendar cal = Calendar.getInstance(dbTimeZone);
        long upperBoundMillis = System.currentTimeMillis() - timestampDelayMs;
        switch (mode) {
            case BULK -> {
                // no parameters
            }
            case INCREMENTING -> stmt.setLong(1, lastIncrementing);
            case TIMESTAMP -> {
                stmt.setTimestamp(1, new Timestamp(lastTimestampMillis < 0 ? 0 : lastTimestampMillis), cal);
                stmt.setTimestamp(2, new Timestamp(upperBoundMillis), cal);
            }
            case TIMESTAMP_INCREMENTING -> {
                long baseTs = lastTimestampMillis < 0 ? 0 : lastTimestampMillis;
                stmt.setTimestamp(1, new Timestamp(baseTs), cal);
                stmt.setLong(2, lastIncrementing);
                stmt.setTimestamp(3, new Timestamp(baseTs), cal);
                stmt.setTimestamp(4, new Timestamp(upperBoundMillis), cal);
            }
        }
    }

    private List<QueriedRow> extractAndAdvance(ResultSet rs) throws SQLException {
        List<QueriedRow> rows = new ArrayList<>();
        ResultSetMetaData meta = rs.getMetaData();
        int columnCount = meta.getColumnCount();
        Calendar cal = Calendar.getInstance(dbTimeZone);

        while (rs.next()) {
            Map<String, Object> columns = new LinkedHashMap<>();
            for (int i = 1; i <= columnCount; i++) {
                columns.put(meta.getColumnLabel(i), rs.getObject(i));
            }

            if (mode == QueryMode.INCREMENTING || mode == QueryMode.TIMESTAMP_INCREMENTING) {
                long value = rs.getLong(incrementingColumn);
                if (value > lastIncrementing) {
                    lastIncrementing = value;
                }
            }
            if (mode == QueryMode.TIMESTAMP || mode == QueryMode.TIMESTAMP_INCREMENTING) {
                Timestamp ts = rs.getTimestamp(timestampColumn, cal);
                if (ts != null) {
                    long millis = ts.getTime();
                    if (millis > lastTimestampMillis) {
                        lastTimestampMillis = millis;
                        if (mode == QueryMode.TIMESTAMP_INCREMENTING) {
                            // New timestamp bucket: restart the incrementing tie-break from
                            // this row's own value so the next row in the same bucket with a
                            // *smaller* incrementing value than a previous bucket isn't skipped.
                            lastIncrementing = rs.getLong(incrementingColumn);
                        }
                    }
                }
            }
            if (mode == QueryMode.BULK) {
                bulkRun++;
            }

            rows.add(new QueriedRow(columns, currentOffset()));
        }
        return rows;
    }

    private Map<String, Object> currentOffset() {
        Map<String, Object> offset = new LinkedHashMap<>();
        if (mode == QueryMode.INCREMENTING || mode == QueryMode.TIMESTAMP_INCREMENTING) {
            offset.put(OFFSET_INCREMENTING, lastIncrementing);
        }
        if (mode == QueryMode.TIMESTAMP || mode == QueryMode.TIMESTAMP_INCREMENTING) {
            offset.put(OFFSET_TIMESTAMP, lastTimestampMillis);
        }
        if (mode == QueryMode.BULK) {
            offset.put(OFFSET_BULK_RUN, bulkRun);
        }
        return offset;
    }

    // Visible for tests.
    long lastIncrementing() {
        return lastIncrementing;
    }

    long lastTimestampMillis() {
        return lastTimestampMillis;
    }
}

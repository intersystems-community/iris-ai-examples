package com.intersystems.kafka.connect.iris.sink;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Generates and runs the SQL to write one record's fields to one table,
 * for whichever {@link InsertMode} the sink is configured with.
 *
 * <p>This class knows nothing about Kafka, batching, retries, or the
 * dead-letter path -- that separation is deliberate, so the SQL-generation
 * logic can be unit-tested against the H2 stand-in
 * ({@code src/test/java/.../sink/IrisTableWriterH2Test.java}) without
 * dragging in {@code SinkTask} lifecycle or Connect framework mocks. See
 * {@link IrisSinkTask} for batching, retry, and dead-lettering.
 *
 * <p>Every method here takes an already-open {@link Connection} and throws
 * the raw {@link SQLException} on failure; the caller (normally
 * {@link IrisSinkTask}) decides whether a given failure means "retry the
 * whole batch" (e.g. connection dropped) or "this one record is bad, send
 * it to the dead-letter path" (e.g. a type or constraint violation).
 */
public class IrisTableWriter {

    private final InsertMode mode;
    private final List<String> pkFields;

    public IrisTableWriter(InsertMode mode, List<String> pkFields) {
        this.mode = mode;
        this.pkFields = pkFields == null ? List.of() : List.copyOf(pkFields);
        if (mode != InsertMode.INSERT && this.pkFields.isEmpty()) {
            throw new IllegalArgumentException("pkFields must be non-empty for insert mode " + mode);
        }
    }

    public static String resolveTableName(String tableNameFormat, String topic) {
        return tableNameFormat.replace("${topic}", topic);
    }

    /** Writes one record to {@code table}. Column order follows {@code fields}' iteration order. */
    public void writeRecord(Connection connection, String table, Map<String, Object> fields) throws SQLException {
        switch (mode) {
            case INSERT -> insert(connection, table, fields);
            case UPSERT_PORTABLE -> upsertPortable(connection, table, fields);
            case UPSERT_NATIVE -> upsertNative(connection, table, fields);
        }
    }

    private void insert(Connection connection, String table, Map<String, Object> fields) throws SQLException {
        List<String> columns = new ArrayList<>(fields.keySet());
        String sql = "INSERT INTO " + table + " (" + String.join(", ", columns) + ") VALUES ("
                + placeholders(columns.size()) + ")";
        try (PreparedStatement stmt = connection.prepareStatement(sql)) {
            bind(stmt, columns, fields, 1);
            stmt.executeUpdate();
        }
    }

    /**
     * Try-UPDATE-then-INSERT-if-nothing-matched. Plain ANSI SQL, deliberately
     * portable across IRIS and the H2 test stand-in -- see this class's javadoc.
     */
    private void upsertPortable(Connection connection, String table, Map<String, Object> fields) throws SQLException {
        List<String> nonPkColumns = new ArrayList<>();
        for (String column : fields.keySet()) {
            if (!pkFields.contains(column)) {
                nonPkColumns.add(column);
            }
        }

        if (!nonPkColumns.isEmpty()) {
            String setClause = nonPkColumns.stream().map(c -> c + " = ?").reduce((a, b) -> a + ", " + b).orElse("");
            String whereClause = pkFields.stream().map(c -> c + " = ?").reduce((a, b) -> a + " AND " + b).orElse("");
            String updateSql = "UPDATE " + table + " SET " + setClause + " WHERE " + whereClause;
            int updated;
            try (PreparedStatement stmt = connection.prepareStatement(updateSql)) {
                int idx = bind(stmt, nonPkColumns, fields, 1);
                bind(stmt, pkFields, fields, idx);
                updated = stmt.executeUpdate();
            }
            if (updated > 0) {
                return;
            }
            insert(connection, table, fields);
            return;
        }

        // Primary-key-only "table": nothing to UPDATE, so fall back to an
        // existence check instead of blindly inserting a duplicate key.
        String existsSql = "SELECT COUNT(*) FROM " + table + " WHERE "
                + pkFields.stream().map(c -> c + " = ?").reduce((a, b) -> a + " AND " + b).orElse("");
        try (PreparedStatement stmt = connection.prepareStatement(existsSql)) {
            bind(stmt, pkFields, fields, 1);
            try (var rs = stmt.executeQuery()) {
                rs.next();
                if (rs.getInt(1) > 0) {
                    return; // already present; nothing to update, pk-only row is unchanged
                }
            }
        }
        insert(connection, table, fields);
    }

    /**
     * IRIS's native upsert: {@code INSERT OR UPDATE table (cols) VALUES (...)}.
     * Documented at https://docs.intersystems.com (RSQL_insertorupdate) -- first
     * attempts an insert, and on a unique-key violation, updates the existing
     * row instead. NOT exercised by this project's test suite: H2 does not
     * implement this syntax. See STATUS.md before enabling insert.mode=upsert_native.
     */
    private void upsertNative(Connection connection, String table, Map<String, Object> fields) throws SQLException {
        List<String> columns = new ArrayList<>(fields.keySet());
        String sql = "INSERT OR UPDATE " + table + " (" + String.join(", ", columns) + ") VALUES ("
                + placeholders(columns.size()) + ")";
        try (PreparedStatement stmt = connection.prepareStatement(sql)) {
            bind(stmt, columns, fields, 1);
            stmt.executeUpdate();
        }
    }

    private static String placeholders(int count) {
        return String.join(", ", java.util.Collections.nCopies(count, "?"));
    }

    /** Binds {@code columns} (in order) from {@code fields} starting at 1-based {@code startIndex}; returns the next free index. */
    private static int bind(PreparedStatement stmt, List<String> columns, Map<String, Object> fields, int startIndex)
            throws SQLException {
        int idx = startIndex;
        for (String column : columns) {
            stmt.setObject(idx++, fields.get(column));
        }
        return idx;
    }

    /** Converts an insertable/updatable field map into a defensive, ordered copy. */
    public static Map<String, Object> orderedCopy(Map<String, Object> fields) {
        return new LinkedHashMap<>(fields);
    }
}

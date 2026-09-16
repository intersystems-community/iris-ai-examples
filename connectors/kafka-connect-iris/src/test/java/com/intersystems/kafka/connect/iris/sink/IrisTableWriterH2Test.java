package com.intersystems.kafka.connect.iris.sink;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Exercises {@link IrisTableWriter}'s SQL against H2.
 *
 * <p><b>H2 is a STAND-IN FOR IRIS, NOT IRIS.</b> See
 * {@code source/TableQuerierH2Test}'s javadoc for the general caveat. It
 * matters especially here: {@link InsertMode#UPSERT_NATIVE} generates
 * IRIS's {@code INSERT OR UPDATE} statement, which H2 does not implement,
 * so that code path has NO automated test coverage in this repository at
 * all -- not "tested against a stand-in", genuinely untested. Only
 * {@link InsertMode#INSERT} and {@link InsertMode#UPSERT_PORTABLE} (plain
 * ANSI SQL) are exercised here. See STATUS.md.
 */
class IrisTableWriterH2Test {

    private static final AtomicInteger DB_COUNTER = new AtomicInteger();
    private Connection connection;

    @BeforeEach
    void setUp() throws SQLException {
        connection = DriverManager.getConnection(
                "jdbc:h2:mem:tablewriter" + DB_COUNTER.incrementAndGet() + ";DB_CLOSE_DELAY=-1");
        try (Statement stmt = connection.createStatement()) {
            stmt.execute("CREATE TABLE Patient (id BIGINT PRIMARY KEY, name VARCHAR(100), active BOOLEAN)");
        }
    }

    @AfterEach
    void tearDown() throws SQLException {
        connection.close();
    }

    private Map<String, Object> row(long id, String name, boolean active) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("ID", id);
        fields.put("NAME", name);
        fields.put("ACTIVE", active);
        return fields;
    }

    private List<Map<String, Object>> selectAll() throws SQLException {
        List<Map<String, Object>> rows = new java.util.ArrayList<>();
        try (Statement stmt = connection.createStatement();
                ResultSet rs = stmt.executeQuery("SELECT id, name, active FROM Patient ORDER BY id")) {
            while (rs.next()) {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("ID", rs.getLong("id"));
                r.put("NAME", rs.getString("name"));
                r.put("ACTIVE", rs.getBoolean("active"));
                rows.add(r);
            }
        }
        return rows;
    }

    // ---- InsertMode.INSERT ----

    @Test
    void insertModeInsertsANewRow() throws SQLException {
        IrisTableWriter writer = new IrisTableWriter(InsertMode.INSERT, List.of());
        writer.writeRecord(connection, "Patient", row(1, "Alice", true));

        List<Map<String, Object>> rows = selectAll();
        assertEquals(1, rows.size());
        assertEquals("Alice", rows.get(0).get("NAME"));
    }

    @Test
    void insertModeThrowsOnDuplicateKey() throws SQLException {
        IrisTableWriter writer = new IrisTableWriter(InsertMode.INSERT, List.of());
        writer.writeRecord(connection, "Patient", row(1, "Alice", true));

        assertThrows(SQLException.class,
                () -> writer.writeRecord(connection, "Patient", row(1, "Duplicate", false)),
                "a primary-key collision under insert.mode=insert must surface as a per-row failure, "
                        + "not be silently swallowed -- that's what lets IrisSinkTask route it to the "
                        + "dead-letter path instead of the rest of the batch");
    }

    // ---- InsertMode.UPSERT_PORTABLE ----

    @Test
    void upsertPortableInsertsWhenTheRowDoesNotExist() throws SQLException {
        IrisTableWriter writer = new IrisTableWriter(InsertMode.UPSERT_PORTABLE, List.of("ID"));
        writer.writeRecord(connection, "Patient", row(1, "Alice", true));

        List<Map<String, Object>> rows = selectAll();
        assertEquals(1, rows.size());
        assertEquals("Alice", rows.get(0).get("NAME"));
    }

    @Test
    void upsertPortableUpdatesWhenTheRowAlreadyExists() throws SQLException {
        IrisTableWriter writer = new IrisTableWriter(InsertMode.UPSERT_PORTABLE, List.of("ID"));
        writer.writeRecord(connection, "Patient", row(1, "Alice", true));
        writer.writeRecord(connection, "Patient", row(1, "Alice Updated", false));

        List<Map<String, Object>> rows = selectAll();
        assertEquals(1, rows.size(), "must update in place, not insert a second row");
        assertEquals("Alice Updated", rows.get(0).get("NAME"));
        assertEquals(false, rows.get(0).get("ACTIVE"));
    }

    @Test
    void upsertPortableHandlesAMixedBatchOfNewAndExistingRows() throws SQLException {
        IrisTableWriter writer = new IrisTableWriter(InsertMode.UPSERT_PORTABLE, List.of("ID"));
        writer.writeRecord(connection, "Patient", row(1, "Alice", true));

        writer.writeRecord(connection, "Patient", row(1, "Alice V2", true)); // update
        writer.writeRecord(connection, "Patient", row(2, "Bob", true)); // insert

        List<Map<String, Object>> rows = selectAll();
        assertEquals(2, rows.size());
        assertEquals("Alice V2", rows.get(0).get("NAME"));
        assertEquals("Bob", rows.get(1).get("NAME"));
    }

    @Test
    void tableNameFormatSubstitutesTheTopic() {
        assertEquals("Patient", IrisTableWriter.resolveTableName("${topic}", "Patient"));
        assertEquals("iris_Patient", IrisTableWriter.resolveTableName("iris_${topic}", "Patient"));
    }

    @Test
    void constructorRejectsUpsertModeWithoutPkFields() {
        assertThrows(IllegalArgumentException.class,
                () -> new IrisTableWriter(InsertMode.UPSERT_PORTABLE, List.of()));
    }
}

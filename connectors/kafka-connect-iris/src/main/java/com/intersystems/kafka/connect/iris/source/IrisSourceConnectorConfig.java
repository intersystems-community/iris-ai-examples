package com.intersystems.kafka.connect.iris.source;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.apache.kafka.common.config.AbstractConfig;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.common.config.ConfigDef.Importance;
import org.apache.kafka.common.config.ConfigDef.Type;
import org.apache.kafka.common.config.ConfigDef.Width;
import org.apache.kafka.common.config.ConfigException;

/**
 * Config surface and validation for {@link IrisSourceConnector}.
 *
 * <p>Two things here exist specifically to answer the community critique
 * cited in this connector's README -- that IRIS's own built-in Kafka
 * adapters have no real partition support and no non-auto offset handling:
 * <ul>
 *   <li>{@code table.whitelist} is a list, not a single table. The
 *       connector splits it across {@code tasks.max} tasks in
 *       {@link IrisSourceConnector#taskConfigs}, so a multi-table source
 *       actually parallelizes instead of being pinned to one task.</li>
 *   <li>{@code incrementing.initial} and {@code timestamp.initial} let an
 *       operator pin the starting position explicitly on first run,
 *       instead of the connector silently deciding (e.g. always starting
 *       at the current max, which silently drops backlog, or always at
 *       zero/epoch, which can replay an entire large table).</li>
 * </ul>
 */
public class IrisSourceConnectorConfig extends AbstractConfig {

    // -- Connection --
    public static final String CONNECTION_URL_CONFIG = "connection.url";
    private static final String CONNECTION_URL_DOC =
            "IRIS JDBC connection URL, e.g. jdbc:IRIS://iris-host:1972/USER. "
            + "Must start with 'jdbc:IRIS:' (case-insensitive) -- see "
            + "https://docs.intersystems.com for the JDBC connection reference.";

    public static final String CONNECTION_USER_CONFIG = "connection.user";
    private static final String CONNECTION_USER_DOC = "IRIS username used to open the JDBC connection.";

    public static final String CONNECTION_PASSWORD_CONFIG = "connection.password";
    private static final String CONNECTION_PASSWORD_DOC = "IRIS password used to open the JDBC connection.";

    // -- Table selection --
    public static final String TABLE_WHITELIST_CONFIG = "table.whitelist";
    private static final String TABLE_WHITELIST_DOC =
            "Comma-separated list of tables to poll. Mutually exclusive with 'query'. "
            + "Each table becomes an independently-offset, independently-partitioned unit of "
            + "work distributed across tasks.max tasks.";

    public static final String QUERY_CONFIG = "query";
    private static final String QUERY_DOC =
            "A single custom SELECT to run instead of polling whole tables. Mutually "
            + "exclusive with table.whitelist. Because a single arbitrary query cannot be "
            + "safely split, query mode always runs on exactly one task regardless of tasks.max.";

    // -- Mode --
    public static final String MODE_CONFIG = "mode";
    private static final String MODE_DOC =
            "One of 'bulk', 'incrementing', 'timestamp', 'timestamp+incrementing'. "
            + "'bulk' re-reads the full table/query every poll. 'incrementing' tracks a "
            + "strictly-increasing numeric column. 'timestamp' tracks a modification-time "
            + "column (subject to the driver's timestamp granularity). "
            + "'timestamp+incrementing' tracks both, which is the only mode that gives "
            + "exactly-once delivery ordering when many rows can share one timestamp.";

    public static final String INCREMENTING_COLUMN_CONFIG = "incrementing.column.name";
    private static final String INCREMENTING_COLUMN_DOC =
            "Name of the strictly-increasing column to use in 'incrementing' and "
            + "'timestamp+incrementing' modes.";

    public static final String INCREMENTING_INITIAL_CONFIG = "incrementing.initial";
    private static final String INCREMENTING_INITIAL_DOC =
            "Starting value (exclusive) for the incrementing column when no offset has been "
            + "committed yet for a table, e.g. after a fresh deployment or an offset-topic wipe. "
            + "Default -1 means 'start from the beginning'. This is explicit and non-auto on "
            + "purpose: it must be set by an operator, not guessed by the connector.";

    public static final String TIMESTAMP_COLUMN_CONFIG = "timestamp.column.name";
    private static final String TIMESTAMP_COLUMN_DOC =
            "Name of the modification-timestamp column to use in 'timestamp' and "
            + "'timestamp+incrementing' modes.";

    public static final String TIMESTAMP_INITIAL_CONFIG = "timestamp.initial";
    private static final String TIMESTAMP_INITIAL_DOC =
            "Starting epoch-millis value (exclusive) for the timestamp column when no offset "
            + "has been committed yet for a table. Default -1 means 'start from the beginning' "
            + "(epoch 0).";

    public static final String TIMESTAMP_DELAY_MS_CONFIG = "timestamp.delay.ms";
    private static final String TIMESTAMP_DELAY_MS_DOC =
            "How far behind 'now' the upper bound of a timestamp-mode query stays, in "
            + "milliseconds. Guards against missing a row whose commit timestamp is written "
            + "slightly after it becomes visible to a concurrent poll. 0 disables the guard.";

    // -- Polling / batching --
    public static final String POLL_INTERVAL_MS_CONFIG = "poll.interval.ms";
    private static final String POLL_INTERVAL_MS_DOC = "How often, in milliseconds, each task polls its tables.";

    public static final String BATCH_MAX_ROWS_CONFIG = "batch.max.rows";
    private static final String BATCH_MAX_ROWS_DOC =
            "Maximum rows fetched per table per poll. Bounds both memory use and how long a "
            + "single poll can block a task.";

    // -- Topic --
    public static final String TOPIC_PREFIX_CONFIG = "topic.prefix";
    private static final String TOPIC_PREFIX_DOC =
            "Prefix prepended to each table name (or, in query mode, used as the full topic "
            + "name) to form the destination topic.";

    public static final String DB_TIMEZONE_CONFIG = "db.timezone";
    private static final String DB_TIMEZONE_DOC =
            "Timezone the database server uses for TIMESTAMP columns with no explicit zone, "
            + "used to interpret timestamp-mode bounds correctly. Default UTC.";

    public static final ConfigDef CONFIG_DEF = baseConfigDef();

    public IrisSourceConnectorConfig(Map<String, String> props) {
        super(CONFIG_DEF, props);
        validateTableSelection();
        validateModeColumns();
    }

    private static ConfigDef baseConfigDef() {
        return new ConfigDef()
                .define(CONNECTION_URL_CONFIG, Type.STRING, ConfigDef.NO_DEFAULT_VALUE,
                        new JdbcUrlValidator(), Importance.HIGH, CONNECTION_URL_DOC,
                        "Connection", 1, Width.LONG, "IRIS JDBC URL")
                .define(CONNECTION_USER_CONFIG, Type.STRING, "", Importance.HIGH, CONNECTION_USER_DOC,
                        "Connection", 2, Width.MEDIUM, "IRIS user")
                .define(CONNECTION_PASSWORD_CONFIG, Type.PASSWORD, "", Importance.HIGH, CONNECTION_PASSWORD_DOC,
                        "Connection", 3, Width.MEDIUM, "IRIS password")
                .define(TABLE_WHITELIST_CONFIG, Type.LIST, List.of(), Importance.HIGH, TABLE_WHITELIST_DOC,
                        "Table selection", 1, Width.LONG, "Table whitelist")
                .define(QUERY_CONFIG, Type.STRING, "", Importance.HIGH, QUERY_DOC,
                        "Table selection", 2, Width.LONG, "Custom query")
                .define(MODE_CONFIG, Type.STRING, "bulk", new ModeValidator(), Importance.HIGH, MODE_DOC,
                        "Mode", 1, Width.MEDIUM, "Mode")
                .define(INCREMENTING_COLUMN_CONFIG, Type.STRING, "", Importance.MEDIUM, INCREMENTING_COLUMN_DOC,
                        "Mode", 2, Width.MEDIUM, "Incrementing column")
                .define(INCREMENTING_INITIAL_CONFIG, Type.LONG, -1L, Importance.MEDIUM, INCREMENTING_INITIAL_DOC,
                        "Mode", 3, Width.SHORT, "Incrementing initial offset")
                .define(TIMESTAMP_COLUMN_CONFIG, Type.STRING, "", Importance.MEDIUM, TIMESTAMP_COLUMN_DOC,
                        "Mode", 4, Width.MEDIUM, "Timestamp column")
                .define(TIMESTAMP_INITIAL_CONFIG, Type.LONG, -1L, Importance.MEDIUM, TIMESTAMP_INITIAL_DOC,
                        "Mode", 5, Width.SHORT, "Timestamp initial offset")
                .define(TIMESTAMP_DELAY_MS_CONFIG, Type.LONG, 0L, ConfigDef.Range.atLeast(0L), Importance.LOW,
                        TIMESTAMP_DELAY_MS_DOC, "Mode", 6, Width.SHORT, "Timestamp delay (ms)")
                .define(POLL_INTERVAL_MS_CONFIG, Type.LONG, 5000L, ConfigDef.Range.atLeast(1L), Importance.MEDIUM,
                        POLL_INTERVAL_MS_DOC, "Polling", 1, Width.SHORT, "Poll interval (ms)")
                .define(BATCH_MAX_ROWS_CONFIG, Type.INT, 1000, ConfigDef.Range.atLeast(1), Importance.MEDIUM,
                        BATCH_MAX_ROWS_DOC, "Polling", 2, Width.SHORT, "Batch max rows")
                .define(TOPIC_PREFIX_CONFIG, Type.STRING, ConfigDef.NO_DEFAULT_VALUE, new NonEmptyValidator(),
                        Importance.HIGH, TOPIC_PREFIX_DOC, "Topic", 1, Width.MEDIUM, "Topic prefix")
                .define(DB_TIMEZONE_CONFIG, Type.STRING, "UTC", Importance.LOW, DB_TIMEZONE_DOC,
                        "Mode", 7, Width.SHORT, "DB timezone");
    }

    private void validateTableSelection() {
        List<String> tables = getList(TABLE_WHITELIST_CONFIG);
        String query = getString(QUERY_CONFIG).trim();
        boolean hasTables = tables != null && !tables.isEmpty();
        boolean hasQuery = !query.isEmpty();
        if (hasTables == hasQuery) {
            throw new ConfigException(
                    TABLE_WHITELIST_CONFIG,
                    tables,
                    "Exactly one of '" + TABLE_WHITELIST_CONFIG + "' or '" + QUERY_CONFIG
                            + "' must be set (not both, not neither).");
        }
    }

    private void validateModeColumns() {
        QueryMode mode = QueryMode.fromConfig(getString(MODE_CONFIG));
        boolean needsIncrementing = mode == QueryMode.INCREMENTING || mode == QueryMode.TIMESTAMP_INCREMENTING;
        boolean needsTimestamp = mode == QueryMode.TIMESTAMP || mode == QueryMode.TIMESTAMP_INCREMENTING;
        if (needsIncrementing && getString(INCREMENTING_COLUMN_CONFIG).trim().isEmpty()) {
            throw new ConfigException(INCREMENTING_COLUMN_CONFIG,
                    getString(INCREMENTING_COLUMN_CONFIG),
                    "'" + INCREMENTING_COLUMN_CONFIG + "' is required when mode='" + mode.configValue() + "'.");
        }
        if (needsTimestamp && getString(TIMESTAMP_COLUMN_CONFIG).trim().isEmpty()) {
            throw new ConfigException(TIMESTAMP_COLUMN_CONFIG,
                    getString(TIMESTAMP_COLUMN_CONFIG),
                    "'" + TIMESTAMP_COLUMN_CONFIG + "' is required when mode='" + mode.configValue() + "'.");
        }
    }

    public QueryMode mode() {
        return QueryMode.fromConfig(getString(MODE_CONFIG));
    }

    public boolean isQueryMode() {
        return !getString(QUERY_CONFIG).trim().isEmpty();
    }

    /** Validates the URL scheme without requiring network access. */
    static class JdbcUrlValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            if (value == null) {
                throw new ConfigException(name, value, "must not be null");
            }
            String url = value.toString().trim();
            if (!url.toLowerCase(Locale.ROOT).startsWith("jdbc:iris:")) {
                throw new ConfigException(name, value,
                        "must start with 'jdbc:IRIS:' (e.g. jdbc:IRIS://host:1972/USER). "
                                + "Got: " + url);
            }
        }
    }

    static class ModeValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            if (value == null) {
                throw new ConfigException(name, value, "must not be null");
            }
            try {
                QueryMode.fromConfig(value.toString());
            } catch (IllegalArgumentException e) {
                throw new ConfigException(name, value,
                        "must be one of " + Arrays.toString(QueryMode.values())
                                + " (as 'bulk', 'incrementing', 'timestamp', or 'timestamp+incrementing')");
            }
        }
    }

    static class NonEmptyValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            if (value == null || value.toString().trim().isEmpty()) {
                throw new ConfigException(name, value, "must not be empty");
            }
        }
    }
}

package com.intersystems.kafka.connect.iris.sink;

import java.util.List;
import java.util.Locale;
import org.apache.kafka.common.config.AbstractConfig;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.common.config.ConfigDef.Importance;
import org.apache.kafka.common.config.ConfigDef.Type;
import org.apache.kafka.common.config.ConfigDef.Width;
import org.apache.kafka.common.config.ConfigException;

import java.util.Map;

/** Config surface and validation for {@link IrisSinkConnector}. */
public class IrisSinkConnectorConfig extends AbstractConfig {

    public static final String CONNECTION_URL_CONFIG = "connection.url";
    private static final String CONNECTION_URL_DOC =
            "IRIS JDBC connection URL, e.g. jdbc:IRIS://iris-host:1972/USER.";

    public static final String CONNECTION_USER_CONFIG = "connection.user";
    private static final String CONNECTION_USER_DOC = "IRIS username used to open the JDBC connection.";

    public static final String CONNECTION_PASSWORD_CONFIG = "connection.password";
    private static final String CONNECTION_PASSWORD_DOC = "IRIS password used to open the JDBC connection.";

    public static final String TABLE_NAME_FORMAT_CONFIG = "table.name.format";
    private static final String TABLE_NAME_FORMAT_DOC =
            "Destination table name. May contain '${topic}', which is replaced with the "
            + "record's topic name -- lets one sink connector fan records from several topics "
            + "out to correspondingly-named tables.";

    public static final String PK_FIELDS_CONFIG = "pk.fields";
    private static final String PK_FIELDS_DOC =
            "Comma-separated list of field names in the record value that form the primary "
            + "key. Required for insert.mode=upsert (either variant); ignored (and may be "
            + "empty) for insert.mode=insert.";

    public static final String INSERT_MODE_CONFIG = "insert.mode";
    private static final String INSERT_MODE_DOC =
            "One of 'insert', 'upsert' (alias for the tested, portable upsert strategy), "
            + "'upsert_portable', or 'upsert_native'. See InsertMode's javadoc for what each "
            + "one does and, for the native mode, why it carries extra risk.";

    public static final String BATCH_SIZE_CONFIG = "batch.size";
    private static final String BATCH_SIZE_DOC =
            "Maximum records written per JDBC batch. Larger batches amortize round-trip cost "
            + "but hold a transaction open longer and make a single bad row's blast radius bigger.";

    public static final String MAX_RETRIES_CONFIG = "max.retries";
    private static final String MAX_RETRIES_DOC =
            "Number of times a failed batch is retried (with backoff) before its records are "
            + "routed to the dead-letter path instead.";

    public static final String RETRY_BACKOFF_MS_CONFIG = "retry.backoff.ms";
    private static final String RETRY_BACKOFF_MS_DOC = "Backoff between batch write retries, in milliseconds.";

    public static final ConfigDef CONFIG_DEF = baseConfigDef();

    public IrisSinkConnectorConfig(Map<String, String> props) {
        super(CONFIG_DEF, props);
        validatePkFields();
    }

    private static ConfigDef baseConfigDef() {
        return new ConfigDef()
                .define(CONNECTION_URL_CONFIG, Type.STRING, ConfigDef.NO_DEFAULT_VALUE,
                        new UrlValidator(), Importance.HIGH, CONNECTION_URL_DOC,
                        "Connection", 1, Width.LONG, "IRIS JDBC URL")
                .define(CONNECTION_USER_CONFIG, Type.STRING, "", Importance.HIGH, CONNECTION_USER_DOC,
                        "Connection", 2, Width.MEDIUM, "IRIS user")
                .define(CONNECTION_PASSWORD_CONFIG, Type.PASSWORD, "", Importance.HIGH, CONNECTION_PASSWORD_DOC,
                        "Connection", 3, Width.MEDIUM, "IRIS password")
                .define(TABLE_NAME_FORMAT_CONFIG, Type.STRING, "${topic}", Importance.HIGH, TABLE_NAME_FORMAT_DOC,
                        "Table", 1, Width.MEDIUM, "Table name format")
                .define(PK_FIELDS_CONFIG, Type.LIST, List.of(), Importance.HIGH, PK_FIELDS_DOC,
                        "Table", 2, Width.MEDIUM, "Primary key fields")
                .define(INSERT_MODE_CONFIG, Type.STRING, "upsert", new InsertModeValidator(), Importance.HIGH,
                        INSERT_MODE_DOC, "Table", 3, Width.MEDIUM, "Insert mode")
                .define(BATCH_SIZE_CONFIG, Type.INT, 500, ConfigDef.Range.atLeast(1), Importance.MEDIUM,
                        BATCH_SIZE_DOC, "Write", 1, Width.SHORT, "Batch size")
                .define(MAX_RETRIES_CONFIG, Type.INT, 3, ConfigDef.Range.atLeast(0), Importance.MEDIUM,
                        MAX_RETRIES_DOC, "Write", 2, Width.SHORT, "Max retries")
                .define(RETRY_BACKOFF_MS_CONFIG, Type.LONG, 1000L, ConfigDef.Range.atLeast(0L), Importance.LOW,
                        RETRY_BACKOFF_MS_DOC, "Write", 3, Width.SHORT, "Retry backoff (ms)");
    }

    private void validatePkFields() {
        InsertMode mode = insertMode();
        List<String> pkFields = getList(PK_FIELDS_CONFIG);
        if (mode != InsertMode.INSERT && (pkFields == null || pkFields.isEmpty())) {
            throw new ConfigException(PK_FIELDS_CONFIG, pkFields,
                    "'" + PK_FIELDS_CONFIG + "' is required when '" + INSERT_MODE_CONFIG + "'='"
                            + getString(INSERT_MODE_CONFIG) + "'.");
        }
    }

    public InsertMode insertMode() {
        return InsertMode.fromConfig(getString(INSERT_MODE_CONFIG));
    }

    static class UrlValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            if (value == null) {
                throw new ConfigException(name, value, "must not be null");
            }
            String url = value.toString().trim();
            if (!url.toLowerCase(Locale.ROOT).startsWith("jdbc:iris:")) {
                throw new ConfigException(name, value,
                        "must start with 'jdbc:IRIS:' (e.g. jdbc:IRIS://host:1972/USER). Got: " + url);
            }
        }
    }

    static class InsertModeValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            if (value == null) {
                throw new ConfigException(name, value, "must not be null");
            }
            try {
                InsertMode.fromConfig(value.toString());
            } catch (IllegalArgumentException e) {
                throw new ConfigException(name, value,
                        "must be one of 'insert', 'upsert', 'upsert_portable', 'upsert_native'");
            }
        }
    }
}

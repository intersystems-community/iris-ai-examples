package com.intersystems.kafka.connect.iris.source;

import java.util.Locale;

/**
 * The four polling strategies the source connector supports. These
 * correspond to the {@code mode} config value.
 *
 * <p>{@code BULK} re-reads the whole table on every poll and is only
 * useful for small, low-change reference tables. The other three track a
 * position and only pull rows past it, which is the point of this
 * connector: the community critique of IRIS's built-in Kafka adapters
 * called out the lack of any non-auto offset handling, so every one of
 * these three modes exposes an explicit initial-offset config instead of
 * silently picking one (see {@link IrisSourceConnectorConfig}).
 */
public enum QueryMode {
    BULK,
    INCREMENTING,
    TIMESTAMP,
    TIMESTAMP_INCREMENTING;

    public static QueryMode fromConfig(String value) {
        return QueryMode.valueOf(value.trim().toUpperCase(Locale.ROOT).replace('+', '_').replace('-', '_'));
    }

    public String configValue() {
        return name().toLowerCase(Locale.ROOT).replace('_', '+');
    }
}

package com.intersystems.kafka.connect.iris.sink;

import java.util.Locale;

/**
 * How {@link IrisTableWriter} writes each record.
 *
 * <ul>
 *   <li>{@code INSERT} -- plain insert; a primary-key collision fails the
 *       record (and, depending on {@code insert.mode}, routes it to the
 *       dead-letter path).</li>
 *   <li>{@code UPSERT_PORTABLE} -- try {@code UPDATE}, and if it affects
 *       zero rows, {@code INSERT}. Plain ANSI SQL, works against IRIS and
 *       against the H2 stand-in used in this project's tests, which is why
 *       it is the default.</li>
 *   <li>{@code UPSERT_NATIVE} -- IRIS's own {@code INSERT OR UPDATE}
 *       statement. Real and documented (see the sink connector's README
 *       for the doc citation), but H2 does not support this syntax, so no
 *       automated test in this repository exercises it -- see STATUS.md.
 *       Use only once verified against a real IRIS instance.</li>
 * </ul>
 */
public enum InsertMode {
    INSERT,
    UPSERT_PORTABLE,
    UPSERT_NATIVE;

    public static InsertMode fromConfig(String value) {
        String normalized = value.trim().toUpperCase(Locale.ROOT).replace('-', '_');
        if (normalized.equals("UPSERT")) {
            // "upsert" alone means the safe, tested default.
            return UPSERT_PORTABLE;
        }
        return InsertMode.valueOf(normalized);
    }
}

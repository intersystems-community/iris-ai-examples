package com.intersystems.kafka.connect.iris.jdbc;

import java.sql.Connection;
import java.sql.SQLException;

/**
 * The seam between connector logic and the actual JDBC connection.
 *
 * <p>Every source and sink task talks to the database exclusively through
 * this interface, never through {@code DriverManager} directly. That is
 * what lets tests substitute an in-memory H2 database (a STAND-IN FOR IRIS,
 * NOT IRIS -- see the top-level README/STATUS.md) or a Mockito stub for a
 * real IRIS connection, without any production code caring which one it
 * got.
 */
public interface ConnectionFactory extends AutoCloseable {

    /**
     * Returns a connection to the configured database, opening one if
     * necessary. Implementations that pool or reuse a single connection
     * must be safe to call repeatedly, and must reconnect if the
     * underlying connection has died (see {@link #isClosed()}).
     */
    Connection getConnection() throws SQLException;

    /**
     * @return true if the most recently handed-out connection is known to
     *     be closed or otherwise unusable.
     */
    boolean isClosed() throws SQLException;

    @Override
    void close();
}

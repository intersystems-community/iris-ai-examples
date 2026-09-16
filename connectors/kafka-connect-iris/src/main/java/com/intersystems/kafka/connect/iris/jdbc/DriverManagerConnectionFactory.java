package com.intersystems.kafka.connect.iris.jdbc;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The production {@link ConnectionFactory}: a single lazily-opened JDBC
 * connection obtained through {@link DriverManager}.
 *
 * <p>Against InterSystems IRIS, the JDBC URL is expected to look like
 * {@code jdbc:IRIS://host:1972/NAMESPACE} and the driver class is
 * {@code com.intersystems.jdbc.IRISDriver}, shipped by InterSystems on
 * Maven Central as {@code com.intersystems:intersystems-jdbc} (see
 * STATUS.md for how those coordinates were verified). This class does not
 * hardcode the driver class name via {@code Class.forName} -- JDBC 4+
 * drivers self-register via {@code META-INF/services}, and the
 * intersystems-jdbc jar does this, so a plain {@code DriverManager.getConnection}
 * is sufficient once the driver jar is on the classpath.
 *
 * <p>This class is deliberately never exercised against IRIS in this
 * repository's test suite -- there is no IRIS instance available. It is
 * exercised in tests only insofar as {@link ConnectionFactory} implementations
 * backed by H2 follow the same contract; see STATUS.md.
 */
public class DriverManagerConnectionFactory implements ConnectionFactory {

    private static final Logger log = LoggerFactory.getLogger(DriverManagerConnectionFactory.class);

    private final String url;
    private final Properties connectionProps;

    private volatile Connection connection;

    public DriverManagerConnectionFactory(String url, String user, String password) {
        this.url = url;
        this.connectionProps = new Properties();
        if (user != null) {
            connectionProps.setProperty("user", user);
        }
        if (password != null) {
            connectionProps.setProperty("password", password);
        }
    }

    @Override
    public synchronized Connection getConnection() throws SQLException {
        if (connection == null || connection.isClosed()) {
            log.debug("Opening JDBC connection to {}", url);
            connection = DriverManager.getConnection(url, connectionProps);
        }
        return connection;
    }

    @Override
    public synchronized boolean isClosed() throws SQLException {
        return connection == null || connection.isClosed();
    }

    @Override
    public synchronized void close() {
        if (connection != null) {
            try {
                connection.close();
            } catch (SQLException e) {
                log.warn("Error closing JDBC connection to {}", url, e);
            } finally {
                connection = null;
            }
        }
    }
}

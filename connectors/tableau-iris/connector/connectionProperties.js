// InterSystems IRIS Tableau Connector — connectionProperties.js
//
// Only used for JDBC connectors (confirmed via WebSearch against
// tableau.github.io/connector-plugin-sdk's own docs summary, 2026-09-16).
// Same loading model as connectionBuilder.js — see the comment at the
// top of that file. Returns the java.util.Properties map Tableau passes
// to DriverManager.getConnection(url, props) alongside the JDBC URL from
// connectionBuilder.js.
(function propertiesbuilder(attr) {
    var props = {};

    // "user" / "password" are the standard java.sql.DriverManager
    // property keys (JDBC API contract, not IRIS-specific) — every JDBC
    // driver, including com.intersystems.jdbc.IRISDriver, honors these.
    var rawUsername = attr[connectionHelper.attributeUsername];
    props["user"] = (typeof rawUsername === "string") ? rawUsername : "";

    var rawPassword = attr[connectionHelper.attributePassword];
    props["password"] = (typeof rawPassword === "string") ? rawPassword : "";

    // CONFIRMED (docs.intersystems.com JDBC quick reference, via
    // WebSearch, 2026-09-16): "The ssl parameter enables TLS for both
    // IRISDriver and IRISDataSource, with valid values being true and
    // false, and defaults to false if not set." Only set the property
    // when SSL is actually requested — leaving it unset is equivalent to
    // "false" per that default, and avoids sending a property some IRIS
    // driver version might not expect to see at all.
    //
    // UNVERIFIED beyond this: whether a truststore/certificate path also
    // needs to be supplied as a separate JDBC property for strict TLS
    // validation (as opposed to just enabling TLS) was not confirmed
    // against docs.intersystems.com in this session. See STATUS.md.
    var rawSsl = attr["ssl"];
    var sslRequested = (rawSsl === true) || (rawSsl === "true");
    if (sslRequested) {
        props["ssl"] = "true";
    }

    return props;
})

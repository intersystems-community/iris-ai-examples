// InterSystems IRIS Tableau Connector — connectionBuilder.js
//
// Tableau loads this file's text and evaluates it as a single expression
// that must resolve to a function taking one argument (`attr`, the map of
// normalized connection attributes from connectionResolver.tdr). Tableau's
// own JS engine injects `connectionHelper` into scope at call time — do
// not add `module.exports`, `require`, or anything else that would stop
// this file from being loaded exactly as-is by the real product. The
// unit tests in ../tests load this same file with Node's `vm` module and
// a `connectionHelper` stub instead of modifying it (see
// tests/lib/loadTableauScript.js).
//
// JDBC URL shape: confirmed in connectors/README.md (this repo) and
// independently via WebSearch against docs.intersystems.com,
// 2026-09-16: "jdbc:IRIS://hostname:port/namespace". Driver class
// com.intersystems.jdbc.IRISDriver (not built here — Tableau's JDBC
// driver-locator matches the class from the .jar the person installs;
// see README.md).
(function dsbuilder(attr) {
    var DEFAULT_PORT = 1972;
    var DEFAULT_NAMESPACE = "USER";

    // Tableau's connection-normalizer required-attributes and the field
    // validation-rule in connectionFields.xml should already guarantee a
    // non-empty server, but the normalizer only guards fields it knows
    // about — a hostile or hand-edited .tds/.tdsx can still hand this
    // script a blank, whitespace-only, or missing value, so this checks
    // again rather than trusting the caller.
    var rawServer = attr[connectionHelper.attributeServer];
    var server = (typeof rawServer === "string") ? rawServer.trim() : "";
    if (server.length === 0) {
        throw new Error("InterSystems IRIS connector: 'server' is required.");
    }

    // Port: IRIS's superserver port is numeric 1-65535. Anything else
    // (missing, non-numeric, out of range) falls back to the documented
    // default of 1972 rather than emitting a malformed URL.
    var rawPort = attr[connectionHelper.attributePort];
    var port = DEFAULT_PORT;
    if (rawPort !== undefined && rawPort !== null && String(rawPort).trim().length > 0) {
        var parsedPort = parseInt(String(rawPort).trim(), 10);
        if (!isNaN(parsedPort) && parsedPort >= 1 && parsedPort <= 65535) {
            port = parsedPort;
        }
    }

    // Namespace (Tableau's canonical `dbname` attribute — see
    // connectionFields.xml). It becomes a literal path segment in the
    // JDBC URL, so this rejects "/", "?", "#", and whitespace rather than
    // trying to guess an escaping scheme IRIS's driver was never asked to
    // support: those characters would either break the URL structure or
    // silently get sent to the driver as part of the namespace name.
    var rawNamespace = attr["dbname"];
    var namespace = (typeof rawNamespace === "string") ? rawNamespace.trim() : "";
    if (namespace.length === 0) {
        namespace = DEFAULT_NAMESPACE;
    }
    if (/[\/\?\#\s]/.test(namespace)) {
        throw new Error(
            "InterSystems IRIS connector: namespace '" + namespace +
            "' contains a character ('/', '?', '#', or whitespace) that is " +
            "not valid in a JDBC URL path segment."
        );
    }

    var url = "jdbc:IRIS://" + server + ":" + port + "/" + namespace;

    return [url];
})

// Unit tests for ../connector/connectionBuilder.js, loaded and run as the
// literal file Tableau would package — see lib/loadTableauScript.js.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { loadTableauScript } = require("./lib/loadTableauScript");

const SCRIPT_PATH = path.join(__dirname, "..", "connector", "connectionBuilder.js");

function build(attr, helperOverrides) {
  const dsbuilder = loadTableauScript(SCRIPT_PATH, helperOverrides);
  // The script runs inside a separate vm context/realm, so the array it
  // returns is a different-realm Array — deepEqual's strict identity
  // check on the constructor fails even when the contents match.
  // Array.from() re-materializes it as a normal, same-realm array so the
  // assertions below can compare plain values.
  return Array.from(dsbuilder(attr));
}

test("connectionBuilder: builds jdbc:IRIS URL from server/port/dbname", () => {
  const result = build({ server: "iris.example.com", port: "1972", dbname: "USER" });
  assert.deepEqual(result, ["jdbc:IRIS://iris.example.com:1972/USER"]);
});

test("connectionBuilder: host/port/namespace permutation — custom port and namespace", () => {
  const result = build({ server: "10.0.0.5", port: "51773", dbname: "DEMO" });
  assert.deepEqual(result, ["jdbc:IRIS://10.0.0.5:51773/DEMO"]);
});

test("connectionBuilder: host/port/namespace permutation — hostname with dots", () => {
  const result = build({ server: "db-1.internal.corp.example.com", port: "1972", dbname: "USER" });
  assert.deepEqual(result, ["jdbc:IRIS://db-1.internal.corp.example.com:1972/USER"]);
});

test("connectionBuilder: missing port falls back to documented default 1972", () => {
  const result = build({ server: "host", dbname: "USER" });
  assert.deepEqual(result, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: blank/whitespace-only port falls back to default 1972", () => {
  const result = build({ server: "host", port: "   ", dbname: "USER" });
  assert.deepEqual(result, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: non-numeric port falls back to default 1972 (hostile input)", () => {
  const result = build({ server: "host", port: "not-a-port", dbname: "USER" });
  assert.deepEqual(result, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: out-of-range port falls back to default 1972 (hostile input)", () => {
  const tooHigh = build({ server: "host", port: "999999", dbname: "USER" });
  assert.deepEqual(tooHigh, ["jdbc:IRIS://host:1972/USER"]);

  const negative = build({ server: "host", port: "-1", dbname: "USER" });
  assert.deepEqual(negative, ["jdbc:IRIS://host:1972/USER"]);

  const zero = build({ server: "host", port: "0", dbname: "USER" });
  assert.deepEqual(zero, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: missing dbname falls back to documented default namespace USER", () => {
  const result = build({ server: "host", port: "1972" });
  assert.deepEqual(result, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: blank dbname falls back to default namespace USER", () => {
  const result = build({ server: "host", port: "1972", dbname: "   " });
  assert.deepEqual(result, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: server value is trimmed", () => {
  const result = build({ server: "  host  ", port: "1972", dbname: "USER" });
  assert.deepEqual(result, ["jdbc:IRIS://host:1972/USER"]);
});

test("connectionBuilder: missing server throws (hostile input)", () => {
  assert.throws(() => build({ port: "1972", dbname: "USER" }), /server.*required/i);
});

test("connectionBuilder: empty-string server throws (hostile input)", () => {
  assert.throws(() => build({ server: "", port: "1972", dbname: "USER" }), /server.*required/i);
});

test("connectionBuilder: whitespace-only server throws (hostile input)", () => {
  assert.throws(() => build({ server: "   ", port: "1972", dbname: "USER" }), /server.*required/i);
});

test("connectionBuilder: non-string server (hostile input) is treated as missing and throws", () => {
  assert.throws(() => build({ server: 12345, port: "1972", dbname: "USER" }), /server.*required/i);
  assert.throws(() => build({ server: null, port: "1972", dbname: "USER" }), /server.*required/i);
  assert.throws(() => build({ server: {}, port: "1972", dbname: "USER" }), /server.*required/i);
});

test("connectionBuilder: namespace containing '/' throws rather than corrupting the URL path (hostile input)", () => {
  assert.throws(
    () => build({ server: "host", port: "1972", dbname: "USER/../%SYS" }),
    /namespace/i
  );
});

test("connectionBuilder: namespace containing '?' throws (hostile input, JDBC query-string injection)", () => {
  assert.throws(
    () => build({ server: "host", port: "1972", dbname: "USER?extra=1" }),
    /namespace/i
  );
});

test("connectionBuilder: namespace containing whitespace throws (hostile input)", () => {
  assert.throws(
    () => build({ server: "host", port: "1972", dbname: "USER NAMESPACE" }),
    /namespace/i
  );
});

test("connectionBuilder: namespace containing '#' throws (hostile input)", () => {
  assert.throws(
    () => build({ server: "host", port: "1972", dbname: "USER#frag" }),
    /namespace/i
  );
});

test("connectionBuilder: does not consult attr[\"ssl\"] at all — SSL is a JDBC connection property, not part of the URL (see connectionProperties.test.js)", () => {
  const withSsl = build({ server: "host", port: "1972", dbname: "USER", ssl: "true" });
  const withoutSsl = build({ server: "host", port: "1972", dbname: "USER", ssl: "false" });
  assert.deepEqual(withSsl, withoutSsl);
  assert.deepEqual(withSsl, ["jdbc:IRIS://host:1972/USER"]);
});

// Unit tests for ../connector/connectionProperties.js, loaded and run as
// the literal file Tableau would package — see lib/loadTableauScript.js.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { loadTableauScript } = require("./lib/loadTableauScript");

const SCRIPT_PATH = path.join(__dirname, "..", "connector", "connectionProperties.js");

function buildProps(attr, helperOverrides) {
  const propertiesbuilder = loadTableauScript(SCRIPT_PATH, helperOverrides);
  return propertiesbuilder(attr);
}

test("connectionProperties: sets user/password from username/password attributes", () => {
  const props = buildProps({ username: "_SYSTEM", password: "SYS", ssl: "false" });
  assert.equal(props.user, "_SYSTEM");
  assert.equal(props.password, "SYS");
});

test("connectionProperties: SSL permutation — ssl='true' sets props.ssl to the string 'true'", () => {
  const props = buildProps({ username: "u", password: "p", ssl: "true" });
  assert.equal(props.ssl, "true");
});

test("connectionProperties: SSL permutation — boolean true (not string) also sets props.ssl", () => {
  const props = buildProps({ username: "u", password: "p", ssl: true });
  assert.equal(props.ssl, "true");
});

test("connectionProperties: SSL permutation — ssl='false' omits the ssl property entirely", () => {
  const props = buildProps({ username: "u", password: "p", ssl: "false" });
  assert.equal("ssl" in props, false);
});

test("connectionProperties: SSL permutation — missing ssl attribute omits the ssl property (documented IRIS default is false)", () => {
  const props = buildProps({ username: "u", password: "p" });
  assert.equal("ssl" in props, false);
});

test("connectionProperties: SSL permutation — hostile ssl value (arbitrary string) is treated as false", () => {
  const props = buildProps({ username: "u", password: "p", ssl: "yes-please" });
  assert.equal("ssl" in props, false);
});

test("connectionProperties: missing username (hostile input) becomes empty string, not undefined/throw", () => {
  const props = buildProps({ password: "p", ssl: "false" });
  assert.equal(props.user, "");
});

test("connectionProperties: missing password (hostile input) becomes empty string, not undefined/throw", () => {
  const props = buildProps({ username: "u", ssl: "false" });
  assert.equal(props.password, "");
});

test("connectionProperties: non-string username/password (hostile input) become empty strings rather than leaking objects/numbers into JDBC properties", () => {
  const props = buildProps({ username: 42, password: { evil: true }, ssl: "false" });
  assert.equal(props.user, "");
  assert.equal(props.password, "");
});

test("connectionProperties: always returns a plain object with exactly the expected keys for a given input", () => {
  const withSsl = buildProps({ username: "u", password: "p", ssl: "true" });
  assert.deepEqual(Object.keys(withSsl).sort(), ["password", "ssl", "user"]);

  const withoutSsl = buildProps({ username: "u", password: "p", ssl: "false" });
  assert.deepEqual(Object.keys(withoutSsl).sort(), ["password", "user"]);
});

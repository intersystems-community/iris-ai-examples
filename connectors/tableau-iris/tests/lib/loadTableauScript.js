// Loads a Tableau connector JS file (connectionBuilder.js /
// connectionProperties.js) EXACTLY as shipped — no transpiling, no
// stripping the IIFE, no module.exports added to the source file — and
// returns the callable function it evaluates to, so tests exercise the
// literal bytes Tableau's own JS engine would load.
//
// Tableau's real engine injects a handful of globals before evaluating
// the script (connectionHelper, and for ODBC also driverLocator/logging).
// createConnectionHelperStub() below reproduces only the constant names
// this connector's two scripts actually reference. Those name->string
// mappings (e.g. attributeServer -> "server") are copied from real,
// working samples in tableau/connector-plugin-sdk
// (samples/plugins/postgres_jdbc/connectionBuilder.js and
// samples/components/resolvers/connectionBuilder.js both use
// attr[connectionHelper.attributeServer] / attr["dbname"] against a
// field literally named "server"/"dbname" — see README.md for the full
// citation), not invented for the test.

"use strict";

const fs = require("fs");
const vm = require("vm");

function createConnectionHelperStub() {
  return {
    attributeServer: "server",
    attributePort: "port",
    attributeDatabase: "dbname",
    attributeUsername: "username",
    attributePassword: "password",
    attributeAuthentication: "authentication",
    attributeSSLMode: "sslmode",
  };
}

/**
 * @param {string} filePath absolute path to a connectionBuilder.js /
 *   connectionProperties.js style file.
 * @param {object} [helperOverrides] merged onto the default
 *   connectionHelper stub, for tests that want to exercise a missing or
 *   unexpected connectionHelper shape.
 * @returns {Function} the function the script file evaluates to.
 */
function loadTableauScript(filePath, helperOverrides) {
  const source = fs.readFileSync(filePath, "utf8");
  const connectionHelper = Object.assign(
    createConnectionHelperStub(),
    helperOverrides || {}
  );

  const sandbox = { connectionHelper };
  const context = vm.createContext(sandbox);
  const script = new vm.Script(source, { filename: filePath });
  const result = script.runInContext(context);

  if (typeof result !== "function") {
    throw new Error(
      `${filePath} did not evaluate to a function (got ${typeof result}). ` +
      "Tableau's engine requires the file's top-level expression to be a function."
    );
  }
  return result;
}

module.exports = { loadTableauScript, createConnectionHelperStub };

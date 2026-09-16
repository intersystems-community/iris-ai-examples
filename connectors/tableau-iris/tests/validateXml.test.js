// Validates every XML/TDR/TDD/TCD file in this connector for
// well-formedness, and — when a local clone of tableau/connector-plugin-sdk
// is available — against Tableau's own published XSDs, using the real
// `xmllint` binary (never a hand-rolled parser).
//
// XSD location resolution (first match wins):
//   1. process.env.TABLEAU_SDK_XSD_DIR, if set
//   2. ../../../../ (repo-relative) node_modules/.cache style checkout —
//      not expected to exist; kept only as a documented extension point
// If neither resolves to a directory containing the expected .xsd files,
// every test in this file falls back to well-formedness-only validation
// (xmllint --noout, no --schema) and prints a clear note explaining why,
// per this connector's task brief: "If an XSD is not fetchable, validate
// structurally and say so." This is exactly what happens when this suite
// runs outside the session that originally cloned the SDK — see
// STATUS.md for the real, real schema-validated run's output.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");

const CONNECTOR_DIR = path.join(__dirname, "..", "connector");
const REFERENCE_DIR = path.join(__dirname, "..", "reference");

const XSD_FILES = {
  manifest: "connector_plugin_manifest_latest.xsd",
  fields: "connection_fields.xsd",
  metadata: "connector_plugin_metadata.xsd",
  tdr: "tdr_latest.xsd",
  tdd: "tdd_latest.xsd",
  tcd: "tcd_latest.xsd",
};

function resolveXsdDir() {
  const candidates = [];
  if (process.env.TABLEAU_SDK_XSD_DIR) {
    candidates.push(process.env.TABLEAU_SDK_XSD_DIR);
  }
  for (const dir of candidates) {
    try {
      const files = fs.readdirSync(dir);
      if (files.includes(XSD_FILES.manifest)) {
        return dir;
      }
    } catch {
      // not a directory / not accessible — fall through
    }
  }
  return null;
}

const XSD_DIR = resolveXsdDir();

function haveXmllint() {
  try {
    execFileSync("xmllint", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

const XMLLINT_AVAILABLE = haveXmllint();

function validate(filePath, xsdName) {
  if (!XMLLINT_AVAILABLE) {
    assert.fail(
      "xmllint is not installed in this environment — cannot validate " +
      filePath + " at all, not even for well-formedness. Install libxml2's " +
      "xmllint and re-run."
    );
  }

  const args = ["--noout"];
  let mode;
  if (XSD_DIR) {
    args.push("--schema", path.join(XSD_DIR, xsdName));
    mode = "schema";
  } else {
    mode = "well-formedness-only";
  }
  args.push(filePath);

  try {
    execFileSync("xmllint", args, { stdio: "pipe" });
  } catch (err) {
    const output = (err.stdout || "").toString() + (err.stderr || "").toString();
    assert.fail(
      `xmllint (${mode}) failed for ${filePath}:\n${output}`
    );
  }
  return mode;
}

if (!XSD_DIR) {
  test("NOTE: Tableau XSDs not found via TABLEAU_SDK_XSD_DIR — falling back to well-formedness-only validation for this run", () => {
    // This is intentionally not a failure. It documents, in the test
    // output itself, exactly what tier of validation actually ran — see
    // STATUS.md for the real schema-validated run's pasted output from
    // the session that had a clone of tableau/connector-plugin-sdk.
    assert.ok(true);
  });
}

test("manifest.xml is well-formed" + (XSD_DIR ? " and schema-valid" : ""), () => {
  const mode = validate(path.join(CONNECTOR_DIR, "manifest.xml"), XSD_FILES.manifest);
  assert.ok(mode === "schema" || mode === "well-formedness-only");
});

test("connectionFields.xml is well-formed" + (XSD_DIR ? " and schema-valid" : ""), () => {
  validate(path.join(CONNECTOR_DIR, "connectionFields.xml"), XSD_FILES.fields);
});

test("connectionMetadata.xml is well-formed" + (XSD_DIR ? " and schema-valid" : ""), () => {
  validate(path.join(CONNECTOR_DIR, "connectionMetadata.xml"), XSD_FILES.metadata);
});

test("connectionResolver.tdr is well-formed" + (XSD_DIR ? " and schema-valid" : ""), () => {
  validate(path.join(CONNECTOR_DIR, "connectionResolver.tdr"), XSD_FILES.tdr);
});

test("dialect.tdd is well-formed" + (XSD_DIR ? " and schema-valid" : ""), () => {
  validate(path.join(CONNECTOR_DIR, "dialect.tdd"), XSD_FILES.tdd);
});

test("reference/connection-dialog.tcd (legacy, unwired) is well-formed" + (XSD_DIR ? " and schema-valid" : ""), () => {
  validate(path.join(REFERENCE_DIR, "connection-dialog.tcd"), XSD_FILES.tcd);
});

test("manifest.xml references connection-fields, not connection-dialog (XSD makes them mutually exclusive)", () => {
  const xml = fs.readFileSync(path.join(CONNECTOR_DIR, "manifest.xml"), "utf8");
  assert.match(xml, /<connection-fields\s+file=/);
  assert.doesNotMatch(xml, /<connection-dialog\s+file=/);
});

test("every file:'...' reference in manifest.xml and connectionResolver.tdr points at a file that actually exists", () => {
  for (const [dir, filename] of [
    [CONNECTOR_DIR, "manifest.xml"],
    [CONNECTOR_DIR, "connectionResolver.tdr"],
  ]) {
    const xml = fs.readFileSync(path.join(dir, filename), "utf8");
    const refs = [...xml.matchAll(/file=['"]([^'"]+)['"]/g)].map((m) => m[1]);
    assert.ok(refs.length > 0, `${filename} should reference at least one file`);
    for (const ref of refs) {
      const resolved = path.join(dir, ref);
      assert.ok(
        fs.existsSync(resolved),
        `${filename} references '${ref}' which does not exist at ${resolved}`
      );
    }
  }
});

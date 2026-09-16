// Checks the CAP_* customizations in manifest.xml, and the sql-format /
// function-map choices in dialect.tdd, for INTERNAL consistency against
// the IRIS SQL facts documented in this connector's citation comments
// and in STATUS.md. This does not and cannot confirm those facts are
// correct against a live IRIS instance — it only catches the specific
// failure mode of two files in this connector contradicting each other
// (e.g. manifest.xml claiming LIMIT works while dialect.tdd emits TOP,
// or vice versa).
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

const CONNECTOR_DIR = path.join(__dirname, "..", "connector");
const manifestXml = fs.readFileSync(path.join(CONNECTOR_DIR, "manifest.xml"), "utf8");
const dialectTdd = fs.readFileSync(path.join(CONNECTOR_DIR, "dialect.tdd"), "utf8");
// Comment-stripped view, for checks that must only look at actual XML
// elements/formulas — this file's own documentation comments legitimately
// name things (e.g. "does not use STRPOS") that would otherwise trip a
// naive substring search.
const dialectTddNoComments = dialectTdd.replace(/<!--[\s\S]*?-->/g, "");

function capValue(name) {
  const re = new RegExp(
    `<customization\\s+name=["']${name}["']\\s+value=["']([^"']+)["']`
  );
  const match = manifestXml.match(re);
  return match ? match[1] : undefined;
}

test("CAP_QUERY_TOPSTYLE_TOP=yes is consistent with dialect.tdd's format-select using a Top part", () => {
  assert.equal(capValue("CAP_QUERY_TOPSTYLE_TOP"), "yes");
  assert.match(dialectTdd, /<part\s+name=['"]Top['"]\s+value=['"]TOP %1/);
});

test("CAP_QUERY_TOPSTYLE_LIMIT=no is consistent with dialect.tdd NOT emitting a LIMIT-based Top part", () => {
  assert.equal(capValue("CAP_QUERY_TOPSTYLE_LIMIT"), "no");
  // format-select's Top part must not be the LIMIT style if the
  // capability says LIMIT-style TOP isn't supported.
  const topPartMatch = dialectTdd.match(/<part\s+name=['"]Top['"]\s+value=['"]([^'"]+)['"]/);
  assert.ok(topPartMatch, "dialect.tdd should define a Top format-select part");
  assert.doesNotMatch(topPartMatch[1], /LIMIT/);
});

test("CAP_QUERY_TOPSTYLE_ROWNUM=no is consistent with dialect.tdd not using ROWNUM anywhere", () => {
  assert.equal(capValue("CAP_QUERY_TOPSTYLE_ROWNUM"), "no");
  assert.doesNotMatch(dialectTdd, /ROWNUM/);
});

test("CAP_SELECT_INTO and CAP_SELECT_TOP_INTO are both 'no' (IRIS's INTO clause is Embedded-SQL-only, per docs.intersystems.com RSQL_into — not available over JDBC/Dynamic SQL)", () => {
  assert.equal(capValue("CAP_SELECT_INTO"), "no");
  assert.equal(capValue("CAP_SELECT_TOP_INTO"), "no");
});

test("CAP_CREATE_TEMP_TABLES=no is consistent with dialect.tdd defining no format-create-table block", () => {
  assert.equal(capValue("CAP_CREATE_TEMP_TABLES"), "no");
  // Match the actual element tag, not the plain-English mention of it in
  // this file's own "deliberately not set" documentation comment.
  assert.doesNotMatch(dialectTdd, /<format-create-table/);
});

test("dialect.tdd's id-quotes is the double-quote character, matching docs.intersystems.com's documented delimited-identifier syntax", () => {
  assert.match(dialectTdd, /<id-quotes\s+value='"'\s*\/>/);
});

test("dialect.tdd's format-true/format-false use ANSI-portable (1=1)/(1=0), not vendor keywords TRUE/FALSE this session could not confirm IRIS accepts as literals", () => {
  assert.match(dialectTdd, /<format-true\s+value='\(1=1\)'\s*\/>/);
  assert.match(dialectTdd, /<format-false\s+value='\(1=0\)'\s*\/>/);
});

test("every CAP_* customization in manifest.xml has a preceding citation comment (no un-cited capability claims)", () => {
  // Split into lines, and for every <customization line, require a
  // comment ('<!--') within the preceding 20 lines that isn't itself
  // closed before the customization (i.e. an actual comment block
  // immediately above it, not leftover text from a much earlier one).
  const lines = manifestXml.split("\n");
  const customizationLineIdxs = [];
  lines.forEach((line, idx) => {
    if (/<customization\s+name=/.test(line)) {
      customizationLineIdxs.push(idx);
    }
  });
  assert.ok(customizationLineIdxs.length > 0, "expected at least one <customization> in manifest.xml");

  for (const idx of customizationLineIdxs) {
    const window = lines.slice(Math.max(0, idx - 20), idx).join("\n");
    assert.match(
      window,
      /<!--/,
      `customization at manifest.xml line ${idx + 1} (${lines[idx].trim()}) has no citation comment within 20 lines above it`
    );
  }
});

test("dialect.tdd's function-map does not contain any Postgres-specific builtins that don't exist on IRIS (regression guard against copy-pasting the SDK's postgres_jdbc sample verbatim)", () => {
  const postgresOnlyBuiltins = [
    "STRPOS", "REGEXP_MATCHES", "BOOL_OR", "BOOL_AND", "DATE_TRUNC",
    "EXTRACT(EPOCH", "STRING_AGG", "TO_CHAR", "TO_TIMESTAMP", "SPLIT_PART",
  ];
  for (const builtin of postgresOnlyBuiltins) {
    assert.doesNotMatch(
      dialectTddNoComments,
      new RegExp(builtin.replace(/[()]/g, "\\$&")),
      `dialect.tdd should not reference Postgres-specific builtin '${builtin}'`
    );
  }
});

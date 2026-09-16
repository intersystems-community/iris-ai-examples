# STATUS

## VERIFIED

Everything in this section is backed by real command output produced in
this session (pasted below, not summarized from memory) or by a direct
reading of a real, currently-published source file this session fetched
read-only. No IRIS container, Tableau install, or `.taco` packaging was
run — see UNVERIFIED and HUMAN ACTIONS REQUIRED for what that gap means.

### The connector's file set and schemas match the real Tableau Connector SDK

Cloned read-only in this session (`git clone --depth 1
https://github.com/tableau/connector-plugin-sdk.git`, exit code 0, MIT
license confirmed by reading its `LICENSE` file directly). This
connector's file set (`manifest.xml`, `connectionFields.xml`,
`connectionMetadata.xml`, `connectionResolver.tdr`,
`connectionBuilder.js`, `connectionProperties.js`, `dialect.tdd`) mirrors
that SDK's own current JDBC reference sample,
`samples/plugins/postgres_jdbc/`, read directly from the clone.

### Every XML/TDR/TDD/TCD file validates against Tableau's real, bundled XSDs

Run directly against the cloned SDK's `validation/*.xsd` files with the
system's `xmllint` (libxml2), not a hand-rolled validator:

```
$ xmllint --noout --schema validation/connector_plugin_manifest_latest.xsd connector/manifest.xml
connector/manifest.xml validates
$ xmllint --noout --schema validation/connection_fields.xsd connector/connectionFields.xml
connector/connectionFields.xml validates
$ xmllint --noout --schema validation/connector_plugin_metadata.xsd connector/connectionMetadata.xml
connector/connectionMetadata.xml validates
$ xmllint --noout --schema validation/tdr_latest.xsd connector/connectionResolver.tdr
connector/connectionResolver.tdr validates
$ xmllint --noout --schema validation/tdd_latest.xsd connector/dialect.tdd
connector/dialect.tdd validates
$ xmllint --noout --schema validation/tcd_latest.xsd reference/connection-dialog.tcd
reference/connection-dialog.tcd validates
```

(First pass at `dialect.tdd` actually failed — `sql-format`'s children
are an ordered `xs:sequence` in the XSD, and `id-quotes` was placed
before `format-select` instead of after `format-true`. Reordered, then
it validated. Leaving this in as the real story rather than a clean
first-try narrative.)

### The full offline test suite passes, in both validation modes

`node --version` → `v22.22.2`. Run from `connectors/tableau-iris/tests/`:

**With a local SDK clone available (`TABLEAU_SDK_XSD_DIR` set → real
schema validation, not just well-formedness):**
```
# tests 46
# pass 46
# fail 0
# duration_ms 200.152416
```
(46, not 47 — the "XSDs not found" note-test correctly does not appear
in this mode.)

**Without `TABLEAU_SDK_XSD_DIR` set (the default for anyone who clones
just this connector, no SDK checkout) — falls back to well-formedness-only,
and says so in its own output:**
```
# Subtest: NOTE: Tableau XSDs not found via TABLEAU_SDK_XSD_DIR — falling back to well-formedness-only validation for this run
ok 39 - NOTE: Tableau XSDs not found via TABLEAU_SDK_XSD_DIR — falling back to well-formedness-only validation for this run
...
# tests 47
# pass 47
# fail 0
# duration_ms 214.100473
```

Both full per-test transcripts (all 46/47 `ok` lines) were captured in
this session; the counts and the notable subtest names are reproduced
above rather than the full transcript, to keep this file readable — the
commands to reproduce them exactly are in `README.md`'s Test section.

This covers: `connectionBuilder.js`/`connectionProperties.js` loaded and
executed as the literal files Tableau would package (via Node's `vm`
module — see `tests/lib/loadTableauScript.js`), across host/port/namespace/SSL
permutations and hostile input (missing/blank/non-string server,
non-numeric and out-of-range port, namespace containing `/`, `?`, `#`,
or whitespace); every packaged file's well-formedness and, when
available, schema validity; and internal consistency between
`manifest.xml`'s `CAP_*` flags and `dialect.tdd`'s actual formulas
(including a regression guard against copy-pasting Postgres-only SQL
builtins like `STRPOS`/`REGEXP_MATCHES` into the IRIS dialect).

### IRIS SQL facts backing `dialect.tdd` and `manifest.xml`'s `CAP_*` values

`WebFetch` to `docs.intersystems.com` and `tableau.github.io` was
blocked by this session's egress proxy (`EGRESS_BLOCKED` from both
domains, confirmed directly). The IRIS SQL facts below came from
`WebSearch` result snippets that quote/summarize specific
`docs.intersystems.com` reference pages by name and `KEY=` anchor — real
citations to a real, current, primary source, just not a full page
fetch. Treated as VERIFIED for what a documentation page says; NOT
verified against a running IRIS instance's actual behavior (see
UNVERIFIED).

- **`TOP` works in Dynamic SQL on every current IRIS version** —
  docs.intersystems.com "TOP (SQL)" (`KEY=RSQL_top`): "returns rows... at
  the 'top'... functionally identical to a TOP clause" (re: LIMIT).
- **`LIMIT`/`OFFSET`/`FETCH` also exist, but the three styles are
  mutually exclusive** and IRIS itself raises `SQLCODE -386` if a query
  mixes them — docs.intersystems.com "LIMIT (SQL Clause)"
  (`KEY=RSQL_limit`).
- **The `INTO` clause is Embedded-SQL-only** — docs.intersystems.com
  "INTO (SQL)" (`KEY=RSQL_into`): "The INTO clause and host variables are
  only used in Embedded SQL. They are not used in Dynamic SQL." A JDBC
  client only ever issues Dynamic SQL, so `CAP_SELECT_INTO` /
  `CAP_SELECT_TOP_INTO` = `no` is a documented fact about IRIS, not a
  conservative guess.
- **`||` is a real IRIS string-concatenation operator**, equivalent to
  `CONCAT(a,b)`, and NULL-propagating — docs.intersystems.com "CONCAT
  (SQL)" (`KEY=RSQL_concat` / `RSQL_CONCAT`).
- **Double-quote-delimited identifiers are supported** for ANSI SQL
  compatibility — docs.intersystems.com "Reserved words (SQL)"
  (`KEY=RSQL_reservedwords`) / "Identifiers" (`KEY=GSQL_identifiers`).
- **`DATEADD(datePart, numUnits, date)`, `DATEDIFF(datePart, start, end)`,
  `DATEPART(datePart, date)`** exist as native, T-SQL-shaped function
  calls — docs.intersystems.com "DATEADD (SQL)" (`KEY=RSQL_dateadd`),
  "DATEDIFF (SQL)" (`KEY=RSQL_datediff`), "DATEPART (SQL)"
  (`KEY=RSQL_datepart`).
- **The JDBC `ssl` connection property** is a plain boolean
  (`"true"`/`"false"`, default `"false"`) for both `IRISDriver` and
  `IRISDataSource` — docs.intersystems.com's JDBC quick reference
  (`KEY=BJAVA_REFAPI`), via WebSearch summary.
- **Window functions (`OVER`, `PARTITION BY`, `ROW_NUMBER()`, `RANK()`)
  are documented as supported** — docs.intersystems.com "Overview of
  Window Functions" (`KEY=RSQL_windowfunctions`), "RANK()"
  (`KEY=RSQL_windowrank`), "ROW_NUMBER()" (`KEY=RSQL_windowrownumber`).
  **Flagged, not acted on**: this directly conflicts with the real,
  currently-published `sqlalchemy-iris` driver's own test-suite
  requirement (`requirements.py`: `window_functions` →
  `exclusions.closed()`). That conflict is exactly why this dialect does
  not attempt window-function pushdown at all — see UNVERIFIED.
- **JDBC URL and driver identity**: `jdbc:IRIS://hostname:port/namespace`,
  driver class `com.intersystems.jdbc.IRISDriver`, current Maven Central
  artifact `com.intersystems:intersystems-jdbc` — confirmed both via
  WebSearch against docs.intersystems.com and independently via
  `../README.md` (this repo's own existing shared reference table).

### Independent cross-check against a real, shipped IRIS SQL dialect implementation

`pip download sqlalchemy-iris --no-deps` succeeded (`Successfully
downloaded sqlalchemy-iris`, version 0.20.0, MIT licensed per its
`METADATA`). Unzipped and read directly (`unpacked/sqlalchemy_iris/base.py`,
`requirements.py`) — not summarized from memory:

- `IRISCompiler.visit_true` / `visit_false` return the literal strings
  `"1"` / `"0"` → booleans compile to bit/int, not `TRUE`/`FALSE`
  keywords. Backs `dialect.tdd`'s `format-true`/`format-false` =
  `(1=1)`/`(1=0)`.
- `IRISDialect.supports_modern_pagination = self.server_version_info >=
  (2025, 1)`, and `limit_clause()`/`get_select_precolumns()` switch
  between emitting `TOP %s` (pre-2025.1) and `LIMIT ... OFFSET ...`
  (2025.1+) based on that flag. Backs the `CAP_QUERY_TOPSTYLE_TOP=yes` /
  `CAP_QUERY_TOPSTYLE_LIMIT=no` choice in `manifest.xml` for broad
  version compatibility.
- `get_temp_table_names()` reflects existing tables via
  `table_type == "GLOBAL TEMPORARY"` against `INFORMATION_SCHEMA.TABLES`
  — confirms the type exists, but the driver never issues the `CREATE`
  statement itself, which is why `CAP_CREATE_TEMP_TABLES` is `no` here
  rather than `yes` (see UNVERIFIED).
- `Requirements.intersect` and `Requirements.except_` are both
  `exclusions.closed()` — this driver's own SQLAlchemy compliance suite
  does not consider `INTERSECT`/`EXCEPT` supported. Not encoded as a
  Tableau capability here (Tableau has no direct `CAP_*` for these two
  set operators), but recorded for whoever extends this dialect later.
- `IRISIdentifierPreparer` does not override the base SQLAlchemy
  `IdentifierPreparer`'s quote character, which defaults to `"`. Backs
  `dialect.tdd`'s `id-quotes value='"'`.

## UNVERIFIED

Everything below needs a live IRIS instance and, for most of it, a real
Tableau Desktop/Server install — neither exists in this environment.
This is the honesty-mandated flip side of VERIFIED: nothing here was
executed, and every dialect/capability choice that follows from it is a
best-effort inference, not a confirmed fact.

- **The entire connector has never connected to a real IRIS instance or
  loaded inside real Tableau.** No `.taco` was built, packaged, or
  signed. `connector-packager` (the actual Tableau tool that would do
  that) was never installed or run.
- **Every `dialect.tdd` formula and every `CAP_*` flag** is unverified
  against Tableau's own generated SQL actually executing correctly
  against IRIS. The citation comments in `dialect.tdd`/`manifest.xml`
  mark documentation-level confidence, not execution-level confidence —
  TDVT (Tableau's own verification harness) is the only tool that closes
  that gap, and it requires Windows + a real Tableau install + a live
  IRIS instance, none of which exist here.
- **`CAP_QUERY_TOPSTYLE_LIMIT=no` is a version-compatibility policy
  choice, not a capability gap.** IRIS 2025.1+ does support
  `LIMIT`/`OFFSET`. Tableau capabilities are static per connector
  version and cannot branch on the connected server's actual version, so
  this connector currently targets the lowest common denominator (`TOP`,
  works on every version). A future revision could ship a second,
  2025.1+-only build that uses `LIMIT`/`OFFSET` instead — that decision
  needs a human, not this session.
- **The exact `DATEADD`/`DATEDIFF`/`DATEPART` date-part keyword
  spellings.** `dialect.tdd`'s `<date-parts>` section (if one were
  added) or the raw `%1` substitution currently assumes full English
  words (`year`, `quarter`, ...) will be accepted by IRIS's own
  `DATEADD`/`DATEDIFF`/`DATEPART` — this was NOT confirmed; IRIS may
  expect T-SQL-style abbreviations instead. Currently, no `<date-parts>`
  mapping table is included at all in `dialect.tdd` specifically because
  of this uncertainty — the three date-functions pass Tableau's own
  `localstr` part name straight through unmapped, which is very likely
  wrong for at least some date parts. Confirm against a live instance
  before trusting DATEADD/DATEDIFF/DATEPART pushdown.
- **`DATENAME` and `DATETRUNC`** — this session found no
  docs.intersystems.com page confirming either exists as a native IRIS
  SQL function, and deliberately left both out of `dialect.tdd` rather
  than guess. Tableau will compute these client-side until someone
  confirms (or implements an equivalent formula) against IRIS.
- **Window function pushdown (`RANK`, `ROW_NUMBER`, `OVER`,
  `PARTITION BY`)** — see the direct conflict noted in VERIFIED between
  docs.intersystems.com (says supported) and `sqlalchemy-iris`'s own test
  suite (marks it unsupported for that ORM driver). Not implemented
  either way in `dialect.tdd`. Needs a live instance and an actual
  Tableau LOD/table-calc pushdown test to resolve, one way or the other.
- **`CAP_CREATE_TEMP_TABLES=no`.** IRIS's `GLOBAL TEMPORARY` table type
  exists (confirmed via `sqlalchemy-iris` reflection code), but the exact
  `CREATE TABLE ... GLOBAL TEMPORARY ...` DDL syntax Tableau's
  join-culling optimizer would need to emit was never executed against
  IRIS. Kept conservative (matching the SDK's own `postgres_jdbc`
  sample's choice) rather than guessed at.
- **`<schema enabled='false'/>` in `connectionMetadata.xml`.** IRIS very
  likely exposes `INFORMATION_SCHEMA.SCHEMATA` for browsing, but whether
  Tableau's schema-browsing UI against IRIS actually works correctly
  with it enabled was never tested. Left disabled, matching the SDK's
  own reference sample.
- **SSL beyond the basic `ssl=true/false` toggle** — whether a
  truststore/certificate path needs to be supplied as a separate JDBC
  property for strict TLS certificate validation (as opposed to merely
  enabling TLS) was not confirmed.
- **Tableau Exchange's current certification-tier structure**, TDVT's
  exact "List B"/"List C" change categories, and Tableau Cloud's
  specific constraints on custom JDBC connectors — see `PUBLISHING.md`
  for what little this session could confirm via WebSearch and what it
  explicitly flags as needing a primary-source read.
- **Who at InterSystems owns this** — no access to InterSystems' org
  chart in this session; see `PUBLISHING.md`.

## HUMAN ACTIONS REQUIRED

1. **Confirm the DATEADD/DATEDIFF/DATEPART date-part spellings, and
   DATENAME/DATETRUNC's existence, against a live IRIS instance** (or a
   primary docs.intersystems.com page this session didn't find) before
   trusting any date-function pushdown.
2. **Resolve the window-function conflict** (docs say yes,
   `sqlalchemy-iris` test suite says no) against a live instance, then
   either implement `RANK`/`ROW_NUMBER` pushdown formulas in
   `dialect.tdd` or explicitly document why not.
3. **Stand up a real IRIS instance + Tableau Desktop** and manually test
   every capability in `manifest.xml` and every formula in
   `dialect.tdd` — this is the only way anything in UNVERIFIED moves to
   VERIFIED.
4. **Install and run `connector-packager`** (from
   `tableau/connector-plugin-sdk`, requires JDK 8+ and Python) to
   actually validate, package, and — with a real code-signing
   certificate this session has no access to — sign a `.taco`. See
   `README.md`'s Build section for the exact commands.
5. **Run the full TDVT suite** — requires Windows, a real Tableau
   install, and a live IRIS instance with the SDK's test dataset loaded.
   This session has none of the three.
6. **Identify the actual InterSystems owner** for a Tableau Technology
   Partner relationship (`tableau.com/partners/become`) before doing
   anything with this connector beyond keeping it as a reference
   implementation — see `PUBLISHING.md`.
7. **Re-read `tableau.github.io/connector-plugin-sdk/docs/gallery-submission`
   and `.../docs/package-sign` directly** before submitting anything —
   this session's citations for those two pages are WebSearch-snippet
   derived (direct fetch was blocked by egress policy), not a full
   primary read.
8. **Decide the `class='iris_jdbc'` value in `manifest.xml`
   deliberately.** Per Tableau's own submission rules, this string can
   never change once a connector is accepted — worth a real design
   decision involving whoever owns the partner relationship, not an
   implementation detail inherited from this draft.

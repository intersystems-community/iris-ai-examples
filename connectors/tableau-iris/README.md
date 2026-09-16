# tableau-iris

A Tableau Connector SDK source tree for InterSystems IRIS, over JDBC. This
is the source that a Tableau-provided packager tool turns into a signed
`.taco` file — see "What's NOT here" below for what that packaging step
still requires that this session could not do.

Part of `../` (`connectors/`) — see `../README.md` for the placement
caveat and verification ceiling that applies to everything under
`connectors/`, and `../../CLAUDE.md` for repo-wide rules. Nothing here
touches any IRIS container; there is no running IRIS or Tableau in this
environment.

## What this is

Gap #7 from `../../research/ecosystem-connector-gaps.md`: IRIS reaches
Tableau only through the generic "Other Databases (ODBC/JDBC)" connector.
There is no Tableau Exchange listing and no named IRIS connector, unlike
Power BI, which ships a certified InterSystems connector inside Power BI
Desktop itself.

## Layout

```
connector/                  the actual connector source (what gets packaged)
  manifest.xml               connector-plugin XML: identity, capabilities, file wiring
  connectionFields.xml       Modern Connection Dialog (MCD) field definitions
  connectionMetadata.xml     database/schema browsing behavior
  connectionResolver.tdr     wires connectionBuilder.js / connectionProperties.js + required attrs
  connectionBuilder.js       builds the jdbc:IRIS://host:port/namespace URL
  connectionProperties.js    builds the JDBC Properties map (user/password/ssl)
  dialect.tdd                IRIS SQL dialect: capability overrides, function-map, sql-format
reference/
  connection-dialog.tcd      LEGACY v1 dialog — NOT wired into manifest.xml, see below
tests/                       offline Node test suite (no Docker, no Tableau, no live IRIS)
STATUS.md                    VERIFIED / UNVERIFIED / HUMAN ACTIONS REQUIRED
PUBLISHING.md                Tableau Exchange submission, signing, certification tiers
```

## How the pieces fit together (and where each fact came from)

This connector's shape and every schema were confirmed against a real,
current checkout of `tableau/connector-plugin-sdk` (MIT licensed) cloned
read-only during this session — its bundled `validation/*.xsd` files and
its own `samples/plugins/postgres_jdbc/` reference connector, which is
the SDK's current, actively-maintained example of exactly this kind of
connector (JDBC, modern field-driven dialog). Every non-obvious choice
below has a citation comment in the file it appears in — this README
summarizes them, it doesn't replace them.

- **`manifest.xml`** declares the connector's identity (`class`,
  `superclass='jdbc'`), vendor info, `CAP_*` capability overrides (each
  cited), and which of the other files play which role.
- **Two dialog file formats.** Tableau's manifest schema
  (`connector_plugin_manifest_latest.xsd`) makes `<connection-fields>`
  and `<connection-dialog>` a mutually exclusive `<xs:choice>` — a
  manifest can wire in exactly one, never both (confirmed by reading the
  XSD directly). This connector uses `connectionFields.xml` (the modern,
  field-driven "Modern Connection Dialog" / MCD path), because that's
  what the SDK's own current JDBC sample uses. `reference/connection-dialog.tcd`
  is the legacy v1 alternative, included because the task that produced
  this connector asked for a `.tcd` file explicitly — it validates
  against `tcd_latest.xsd` on its own, but it is **not** referenced by
  `manifest.xml` and is not part of the packaged connector.
- **`connectionFields.xml`** defines the fields the connection dialog
  shows: server, port (default 1972), namespace (Tableau's canonical
  `dbname` attribute, relabeled "Namespace" — IRIS's own term), username,
  password, and an SSL checkbox.
- **`connectionResolver.tdr`** lists the required attributes (must match
  `connectionFields.xml`'s field names exactly) and wires in
  `connectionBuilder.js` and `connectionProperties.js`.
- **`connectionBuilder.js`** builds the JDBC URL:
  `jdbc:IRIS://server:port/namespace`. **`connectionProperties.js`**
  builds the `Properties` map passed alongside it (`user`, `password`,
  and `ssl` when requested).
- **`dialect.tdd`** is deliberately small. It does not port the ~150
  function overrides from the SDK's `postgres_jdbc` sample — most of
  those are Postgres-only builtins (`STRPOS`, `REGEXP_MATCHES`,
  `EXTRACT(EPOCH FROM ...)`) that would produce invalid SQL against IRIS.
  It contains only the handful of overrides this session could actually
  ground in either docs.intersystems.com or a real, currently-shipping
  IRIS SQL dialect implementation.

### The independent, real second source: `sqlalchemy-iris`

Beyond `docs.intersystems.com` (reached via WebSearch, since this
session's egress proxy blocks direct fetches to that domain — see
STATUS.md), this connector's IRIS SQL facts are cross-checked against
`sqlalchemy-iris` (MIT licensed, from PyPI — `pip download sqlalchemy-iris`,
inspected as a real, currently-published dialect implementation that
already had to solve exactly these problems for a different tool). Its
source is what confirmed, independently of any doc page: IRIS's boolean
literals compile to `1`/`0` (bit), `TOP`-vs-`LIMIT` support is gated on
server version (`supports_modern_pagination` only from IRIS 2025.1),
and IRIS exposes reflectable `GLOBAL TEMPORARY` tables.

## Build (packaging into a `.taco`)

Packaging requires Tableau's own `connector-packager` Python tool, which
is part of the `tableau/connector-plugin-sdk` repo but is **not
available in this environment** (no Tableau Desktop/Server, and this
session never installs the packager or attempts to package/sign
anything — see STATUS.md HUMAN ACTIONS REQUIRED). To build it yourself:

```bash
git clone https://github.com/tableau/connector-plugin-sdk.git
cd connector-plugin-sdk/connector-packager
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
python setup.py install

# Validate the XML/TDR/TDD files only (no signing, no .taco):
python -m connector_packager.package --validate-only /path/to/connectors/tableau-iris/connector

# Package without signing (for local Desktop testing):
python -m connector_packager.package /path/to/connectors/tableau-iris/connector --package-only

# Package and sign for distribution (requires a real code-signing keystore):
python -m connector_packager.package /path/to/connectors/tableau-iris/connector -a <alias> -ks <keystore-file>
```

You will also need:
- JDK 8+ (packaging tool requirement)
- The InterSystems IRIS JDBC driver jar (`com.intersystems:intersystems-jdbc`,
  from Maven Central — see `connector/manifest.xml`'s
  `driver-download-link`), placed where Tableau's driver-locator can find
  it, per Tableau's own driver installation docs.
- A running IRIS instance and Tableau Desktop/Server to actually connect
  and test — this session has neither (`../../CLAUDE.md`: "no running
  IRIS, NO Tableau installation, NO Docker daemon" for this task).

## Test

Everything under `tests/` runs fully offline: no Docker, no Tableau
install, no live IRIS, no network access required for a normal run.

```bash
cd connectors/tableau-iris/tests
npm test
# or: node --test
```

This exercises:
- `connectionBuilder.js` and `connectionProperties.js` as the literal
  files Tableau would package (loaded via Node's `vm` module with a
  `connectionHelper` stub — see `tests/lib/loadTableauScript.js`), across
  host/port/namespace/SSL permutations and hostile input (missing
  server, non-numeric port, out-of-range port, namespace containing `/`,
  `?`, `#`, or whitespace, non-string attribute values).
- Every XML/`.tdr`/`.tdd`/`.tcd` file for well-formedness via `xmllint`.
- The same files against Tableau's real XSDs, **if** a local clone of
  `tableau/connector-plugin-sdk` is available: set
  `TABLEAU_SDK_XSD_DIR=/path/to/connector-plugin-sdk/validation` before
  running the tests. Without it, the suite prints a note and falls back
  to well-formedness-only, per this task's brief ("if an XSD is not
  fetchable, validate structurally and say so") — see STATUS.md for the
  real output of both modes.
- Internal consistency between `manifest.xml`'s `CAP_*` flags and
  `dialect.tdd`'s actual SQL formulas (e.g. that `CAP_QUERY_TOPSTYLE_LIMIT=no`
  isn't contradicted by a `LIMIT`-shaped `Top` formula), and a regression
  guard against copy-pasting Postgres-only builtins into the IRIS
  dialect.

Real output from the last run of all of this is pasted in `STATUS.md`.

## What's NOT here (human actions required)

See `STATUS.md` → HUMAN ACTIONS REQUIRED for the full list. In short:
running the actual `connector-packager` tool, packaging/signing a
`.taco`, installing it into a real Tableau Desktop/Server, and
connecting it to a live IRIS instance to see whether the dialect and
capability choices in `dialect.tdd`/`manifest.xml` actually produce
correct, working SQL. None of that was possible in this environment.

# source-iris — Airbyte Source Connector for InterSystems IRIS

An [Airbyte](https://airbyte.com) source connector for
[InterSystems IRIS](https://www.intersystems.com/products/intersystems-iris/), built on
the [Airbyte Python CDK](https://docs.airbyte.com/platform/connector-development/cdk-python).

This closes gap #9 from
[`../../research/ecosystem-connector-gaps.md`](../../research/ecosystem-connector-gaps.md):
Airbyte has 400+ connectors and 170,000+ deployments, and IRIS today exists only as an
InterSystems-internal "Community Opportunity" idea (DPI-I-447) — nobody is building it.
Airbyte is also a multiplier: [Estuary re-lists 500+ Airbyte/Meltano/Stitch
connectors](https://estuary.dev), so one build here propagates into other catalogs.

**Read [`STATUS.md`](STATUS.md) before trusting any claim below** — it separates what
was actually run (with pasted output) from what could not be verified in this
environment (no running IRIS instance, no Docker daemon).

## What this is

- `spec` / `check` / `discover` / `read` implementing the
  [Airbyte Protocol](https://docs.airbyte.com/platform/understanding-airbyte/airbyte-protocol/)
  via `airbyte_cdk.sources.AbstractSource`.
- Full-refresh sync for every discovered table.
- Incremental sync (with correct `STATE` message emission and resume-from-state) for
  every table whose primary key is a single, non-LOB column — see "Incremental sync"
  below for why that's the v1 boundary.
- Catalog discovery from `INFORMATION_SCHEMA.TABLES` / `INFORMATION_SCHEMA.COLUMNS`,
  with a documented IRIS → Airbyte JSON Schema type map (see "Type mapping" below and
  [`docs/iris.md`](docs/iris.md)).
- All SQL identifiers (schema/table/column names) are quoted via
  `source_iris/type_mapping.py::quote_ident` — never string-interpolated raw into a
  query. All values (cursor thresholds, schema filters) are bound DB-API parameters
  (`?`), never spliced into SQL text. See `unit_tests/test_iris_client.py` for tests
  that assert this directly (e.g. a hostile identifier can't break out of its quoting,
  and a schema name/cursor value never appears in the generated SQL text itself).
- All database access goes through a small `DBAPIConnection`/`DBAPICursor` interface
  (`source_iris/db.py`), so every test in `unit_tests/` runs against
  `unit_tests/fakes.py::FakeIrisConnection` — a fake, in-memory DB-API — instead of a
  live IRIS instance. This mirrors this repo's `careconnect-sdoh/evals` pattern:
  provider-agnostic, offline, no Docker, no API key.

## Layout

```
source_iris/            connector package
  source.py               IrisSource(AbstractSource): check_connection(), streams()
  streams.py               IrisTableStream(Stream, CheckpointMixin): per-table stream
  iris_client.py           INFORMATION_SCHEMA discovery + row reads (safe SQL building)
  type_mapping.py          IRIS type -> Airbyte JSON Schema, + quote_ident/quote_qualified
  db.py                    DBAPIConnection/DBAPICursor Protocols + connect_real_iris()
  spec.yaml                connector config JSON Schema (loaded by BaseConnector.spec())
  run.py                   CLI entrypoint (`launch(IrisSource(), sys.argv[1:])`)
unit_tests/              pytest suite, offline, no Docker (see STATUS.md)
  fakes.py                 FakeIrisConnection: in-memory DB-API fake
integration_tests/       Airbyte-convention placeholders (see STATUS.md — not runnable here)
docs/iris.md             Airbyte documentation page (per contribution conventions)
metadata.yaml            Airbyte connector registry metadata
acceptance-test-config.yml  Airbyte Connector Acceptance Test (CAT) config
Dockerfile               manual/local build (see PUBLISHING.md re: current build convention)
pyproject.toml           poetry project (matches other Python-CDK connectors, e.g. source-firebolt)
PUBLISHING.md            the real contribution path to airbytehq/airbyte
STATUS.md                verified / unverified / human actions required
```

## How to run

```bash
cd connectors/airbyte-source-iris
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# spec (no config needed)
python -m source_iris.run spec

# check / discover / read need a config.json, e.g.:
cat > config.json <<'EOF'
{
  "host": "localhost",
  "port": 1972,
  "namespace": "USER",
  "username": "_SYSTEM",
  "password": "SYS"
}
EOF
python -m source_iris.run check --config config.json
python -m source_iris.run discover --config config.json
python -m source_iris.run read --config config.json --catalog integration_tests/configured_catalog.json
```

`check`/`discover`/`read` above require a **live IRIS instance** reachable at that
host/port — there is none in this environment (see STATUS.md). Everything under
`unit_tests/` needs no live IRIS and runs fully offline (see below).

## How to test

```bash
cd connectors/airbyte-source-iris
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest pytest-mock jsonschema
pytest -q
```

No Docker, no live IRIS, no API key. Every test drives the connector through
`unit_tests/fakes.py::FakeIrisConnection`, a fake satisfying `source_iris.db`'s
`DBAPIConnection`/`DBAPICursor` Protocols, including tests that run the actual
`airbyte_cdk.entrypoint.AirbyteEntrypoint` (the real CDK CLI dispatcher) for
`spec`/`check`/`discover`/`read` end to end — see `unit_tests/test_source_read.py`
and `unit_tests/test_spec.py`. Real command output from this run is pasted in
[`STATUS.md`](STATUS.md).

## Type mapping

`source_iris/type_mapping.py::map_iris_type` maps each `INFORMATION_SCHEMA.COLUMNS`
`DATA_TYPE` to an Airbyte JSON Schema field. Full table and the awkward cases (IRIS
`%PosixTime`, streams/LOBs, high-precision `NUMERIC`/`DECIMAL`, `NULL` handling) are
documented in [`docs/iris.md`](docs/iris.md#type-mapping). Short version:

| IRIS `DATA_TYPE` | Airbyte JSON Schema | Note |
| --- | --- | --- |
| `TINYINT`/`SMALLINT`/`INTEGER`/`BIGINT` | `integer` | `BIGINT` also gets `airbyte_type: big_integer` (IRIS BIGINT can exceed the +/-2^53 range a JSON double can represent exactly) |
| `NUMERIC`/`DECIMAL` | `number` | gets `airbyte_type: big_integer`/`big_number` above 15 digits of precision |
| `DOUBLE`/`FLOAT`/`REAL` | `number` | |
| `BIT`/`BOOLEAN` | `boolean` | |
| `CHAR`/`VARCHAR`/`GUID` | `string` | |
| `DATE` | `string`, `format: date` | |
| `TIME` | `string` | |
| `TIMESTAMP` | `string`, `format: date-time` | **also what a `%PosixTime` column reports** — see below |
| `LONGVARCHAR`/`CLOB` (stream) | `string` | best-effort; see "Streams/LOBs" below |
| `LONGVARBINARY`/`BLOB`/`BINARY`/`VARBINARY` (stream) | `string` | best-effort, opaque; no base64 encoding is performed by this connector |
| anything unrecognized | `string` | fallback so `discover()` never fails on one odd column |

Nullable columns get `"type": ["<type>", "null"]`; `NOT NULL` columns get a bare
scalar `"type"`.

### `%PosixTime` — documented, not hand-verified against a live column

`%PosixTime`'s **documented ODBC type is `TIMESTAMP`**
([`%Library.PosixTime` docs](https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=%25Library.PosixTime)),
and `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` reports a column's ODBC type — so a
`%PosixTime` column and a `%TimeStamp` column are **indistinguishable at the catalog
level**; both map to `{"type": "string", "format": "date-time"}` here. The
*logical* (in-memory) representation of `%PosixTime` is an encoded 64-bit signed
integer (1970-01-01 00:00:00 = `1152921504606846976`, not `0`) — but the DB-API driver
is documented to return values in **ODBC display mode** by default, i.e. already
formatted as a normal timestamp string, not that raw encoded integer. **This
connector has not been run against a live `%PosixTime` column to confirm the DB-API
driver actually returns the ODBC-formatted string and not the raw encoded integer** —
there is no running IRIS instance available to check. If it turns out the driver
returns the raw integer for this type, `read_full_refresh`/`read_incremental` will
pass that integer straight through, which downstream would be silently wrong (it would
look like a huge but plausible integer, not obviously broken). **HUMAN ACTION
REQUIRED**: confirm this against a live IRIS instance with a real `%PosixTime` column
before treating this connector's `TIMESTAMP` handling as more than "should work
based on documentation." See STATUS.md.

### Streams/LOBs

IRIS stream columns (`%Stream.GlobalCharacter` / `%Stream.GlobalBinary`, reported as
`LONGVARCHAR`/`LONGVARBINARY`) cannot appear in a `WHERE` or `ORDER BY` clause
(SQLCODE `-313`/`-37`), so:

- a stream column can **never** be chosen as this connector's cursor field or used as
  part of a primary key (`type_mapping.is_lob_type` + `IrisClient`/`IrisSource` enforce
  this — see `source.py::IrisSource._select_cursor_field`);
- this connector still `SELECT`s them in the normal column list for a row (they are
  not excluded from a table's schema/columns), mapped to a best-effort `string`. What
  actually comes back from the DB-API driver for a stream column (a plain string, or a
  stream-handle object requiring `.read()`) has **not been confirmed against a live
  instance**. If the driver returns a handle object rather than a string, this
  connector will currently emit that object's `str()` representation, not its content
  — a real gap, called out in STATUS.md, not silently ignored.

### `NUMERIC`/`DECIMAL` precision

Airbyte's `integer`/`number` JSON Schema types round-trip through a JSON number,
which is an IEEE-754 double: exact only up to `2^53` (~15-16 decimal digits). An IRIS
`NUMERIC`/`DECIMAL(38,0)` or a `BIGINT` near its 64-bit range can lose precision if a
downstream destination naively parses the JSON number as a float. This connector does
not convert those values to strings itself (so nothing points at a live instance is
needed to verify formatting) — it relies on the `airbyte_type: big_integer` /
`big_number` annotations described above to tell precision-aware destinations to
handle them specially, per Airbyte's own documented convention for this exact problem.

### `NULL` handling

A `NULL` column value is passed straight through in the row dict as Python `None`;
`json.dumps` (used by the CDK when serializing the `RECORD` message) renders that as
JSON `null`. A column's Airbyte JSON Schema type only includes `"null"` in its type
union when `INFORMATION_SCHEMA.COLUMNS.IS_NULLABLE = 'YES'` for that column — see
`type_mapping.map_iris_type`.

## Incremental sync — v1 cursor selection

A table becomes incremental-capable only when it has **exactly one primary-key column
that is not a stream/LOB type** (`source.py::IrisSource._select_cursor_field`); that
column is automatically used as the cursor. This connector does **not** let the user
pick an arbitrary cursor column through the Airbyte UI — that is the natural v2
extension (a `cursor_fields` map in the config, or reading `configured_stream.cursor_field`
from the sync catalog instead of auto-selecting). Auto-selecting from the primary key
keeps v1 deterministic and fully testable without a second, freeform config surface.
This means a table with a good `updated_at`-style cursor candidate but a multi-column
or LOB primary key is full-refresh-only in this connector today.

## Known limitations (read before relying on this in production)

- No live IRIS instance was available to build this against (see STATUS.md). Every
  claim about `INFORMATION_SCHEMA` column names, `%PosixTime`'s ODBC behavior, and the
  DB-API driver's exact return types for stream/LOB columns is sourced from
  InterSystems' own documentation (cited throughout `type_mapping.py`, `db.py`,
  `iris_client.py`, and this file) via web search, not hands-on confirmation.
- Cursor selection is automatic (primary key only), not user-configurable — see above.
- Composite primary keys are exposed correctly in the catalog (`primary_key` returns a
  list of single-column lists, per the CDK's documented shape for composite keys), but
  a composite key never becomes a cursor field — only a single-column PK can.
- Views (`INFORMATION_SCHEMA.TABLES.TABLE_TYPE = 'VIEW'`) are never discovered; only
  `'BASE TABLE'` rows are. This is a deliberate v1 scope cut, not an oversight.
- Docker-based Airbyte Connector Acceptance Tests have not been run (no Docker daemon
  in this environment) — see STATUS.md.

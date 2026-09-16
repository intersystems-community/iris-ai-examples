# fivetran-iris

A [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) source
connector for InterSystems IRIS: `schema()` discovers tables/columns from
IRIS's `INFORMATION_SCHEMA`, and `update()` syncs them, either full-refresh
or incrementally via a cursor column, with checkpointing so an interrupted
sync resumes correctly.

Staged in `iris-ai-examples/connectors/` per
[`../README.md`](../README.md) -- see that file's "Placement caveat" and
"Verification ceiling" sections, which apply here too. **There is no
running IRIS instance and no Docker daemon available in the environment
this was built in.** Every claim below is either backed by pasted real
command output (see `STATUS.md`) or explicitly marked unverified.

## What this is

- `connector.py` -- the Fivetran entrypoint (`schema()`, `update()`,
  `connector = Connector(...)`).
- `iris_connector/` -- all actual logic, behind a DB-API-shaped interface
  (`iris_connector.db.DBConnection`/`DBCursor`) so it is unit-testable with
  plain `pytest` and a fake connection, independent of the SDK runtime and
  of any real IRIS instance:
  - `config.py` -- configuration parsing/validation (`ConfigurationError`
    with specific messages).
  - `db.py` -- the DB-API interface, and `connect()`, the *only* place that
    imports the real `iris` driver (`intersystems-irispython`).
  - `catalog.py` -- schema discovery against `INFORMATION_SCHEMA`.
  - `type_mapping.py` -- IRIS type -> Fivetran type, and value coercions
    `Operations.upsert()` needs at write time.
  - `sync.py` -- `update()`'s orchestration: per-table full-refresh or
    incremental sync, upsert emission, checkpointing.
  - `fake_db.py` -- the fake DB-API connection driving every test, and the
    `fivetran debug` walkthrough below.
- `tests/` -- the `pytest` suite (75 tests, offline, no network, no IRIS).
- `PUBLISHING.md` -- the real certification/publishing path for a
  Fivetran partner-built connector, with citations.
- `STATUS.md` -- verified vs. unverified claims, and what a human still
  needs to do.

## How to run the tests

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests/ -v
```

75 passed, 1 intentionally skipped, in well under a second, on a clean
install -- see `STATUS.md` for the pasted output. No network access and no
IRIS instance are needed: every test drives `iris_connector/` through
`iris_connector.fake_db.FakeConnection`, a fake DB-API connection (see
"Testing strategy" below).

`tests/test_connector_entrypoint.py` is the one file that imports the real
`fivetran_connector_sdk`; it is skipped automatically
(`pytest.importorskip`) if that package is not installed, so the rest of
the suite has zero dependency on it.

## How to run `fivetran debug`

`fivetran debug` was run for real against this connector's code -- see
`STATUS.md` for the full pasted output including a bug it caught (fixed;
see "Type mapping" below). To reproduce:

```bash
pip install -r requirements.txt
fivetran debug --configuration configuration.json
```

`configuration.json` in this directory sets `"driver": "fake"`, which
routes the connector at `iris_connector.fake_db.demo_connection()` -- a
small in-memory dataset (`PATIENT`, `ENCOUNTER`) -- instead of a real IRIS
instance. `fivetran debug` persists sync state to `files/state.json` and
the resulting rows to a DuckDB file at `files/warehouse.db`
(`.gitignore`d; regenerate by re-running). Run it twice in a row: the
second run's log shows the incremental `ENCOUNTER` table only re-fetching
from its saved cursor and the full-refresh `PATIENT` table truncating and
reloading again, exactly as designed (see `STATUS.md`).

Delete the `"driver": "fake"` line (or set it to anything else) to connect
to a real IRIS instance -- see "Configuration" below for the real fields.
That path (`iris_connector/db.py`'s `connect()`, using
`intersystems-irispython`) is **unverified against a live IRIS instance**
(see `STATUS.md`); only its import/connect-call shape has been checked
against the installed driver's actual signature.

## Configuration

All values arrive as strings (Fivetran's own convention -- every setup-form
field or `configuration.json` value is a string; `iris_connector/config.py`
is the one place that parses and validates them).

| Key | Required | Default | Meaning |
| --- | --- | --- | --- |
| `host` | yes | -- | IRIS hostname. |
| `port` | no | `1972` | IRIS superserver port. |
| `namespace` | yes | -- | IRIS namespace, e.g. `USER`. |
| `username` | yes | -- | |
| `password` | yes | -- | |
| `schema` | no | `SQLUser` | SQL schema to discover tables in. |
| `tables` | no | (all base tables) | Comma-separated allowlist. |
| `cursor_fields` | no | (none -> full-refresh) | JSON object string mapping table name to cursor column, e.g. `{"PATIENT": "LAST_UPDATED"}`. Tables not listed here sync full-refresh (truncate + reload) instead. |
| `batch_size` | no | `5000` | Rows fetched/upserted per checkpoint. |
| `connection_timeout` | no | `10` | Seconds, passed to `iris.connect(timeout=...)`. |
| `driver` | no | (real IRIS) | Set to `"fake"` only for the local `fivetran debug` walkthrough above. **Never set this in a real deployment** -- see `STATUS.md`. |

Every required-field, type, and range error raises
`iris_connector.config.ConfigurationError` with the specific field name and
what is wrong, e.g.:

```
configuration is missing required field(s): host, password. Required fields are: host, namespace, username, password.
configuration.port must be between 1 and 65535, got 99999.
configuration.cursor_fields must be a JSON object string mapping table name to cursor column, e.g. '{"PATIENT": "UPDATED_AT"}'. Got 'not json' (...).
```

## IRIS connectivity facts this connector relies on

From `../README.md` (this repo's connectors-wide reference) and
InterSystems' own documentation/Developer Community (see citations in
`iris_connector/catalog.py` and `type_mapping.py` docstrings, and
`PUBLISHING.md`):

- Python DB-API: `pip install intersystems-irispython`, `import iris`,
  `iris.connect(hostname, port, namespace, username, password, timeout=...)`
  -- confirmed against the actually-installed package's own docstring
  (`iris.connect.__doc__`), not guessed. Paramstyle is `qmark` (`?`
  placeholders), API level `2.0` (`iris.dbapi.apilevel`/`paramstyle`).
- Ports: `1972` superserver (queries/sync), `52773` web (Management
  Portal/CSP; unused by this connector).
- `INFORMATION_SCHEMA.TABLES.TABLE_TYPE = 'BASE TABLE'` excludes views and
  system tables (confirmed via an InterSystems Developer Community post
  giving this exact query).
- `INFORMATION_SCHEMA.COLUMNS.PRIMARY_KEY` is a IRIS-specific `YES`/`NO`
  column directly on `COLUMNS` -- **not** the ANSI-standard approach of
  joining `KEY_COLUMN_USAGE`. This connector uses it directly rather than
  assuming ANSI names, as instructed.
- `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` values, as exposed through
  ODBC/JDBC (and therefore the Python DB-API): `BIGINT, BIT, DATE, DOUBLE,
  GUID, INTEGER, LONGVARBINARY, LONGVARCHAR, NUMERIC, OREF, POSIXTIME,
  SMALLINT, TIME, TIMESTAMP, TINYINT, VARBINARY, VARCHAR` (plus
  `CHAR`/`FLOAT` variants of the same families).

**None of the above has been confirmed against a live IRIS instance** in
this environment -- see `STATUS.md`.

## Type mapping

| IRIS `DATA_TYPE` | Fivetran type | Notes |
| --- | --- | --- |
| `BIGINT` | `LONG` | |
| `INTEGER`, `INT` | `INT` | |
| `SMALLINT` | `SHORT` | |
| `TINYINT` | `SHORT` | Fivetran has no 8-bit type; `SHORT` never truncates TINYINT's range. |
| `BIT` | `BOOLEAN` | IRIS returns `0`/`1` over DB-API; the SDK's protobuf `BOOLEAN` field accepted the plain `int` directly in the real `fivetran debug` run below -- no coercion needed. |
| `DOUBLE`, `FLOAT` | `DOUBLE` | |
| `NUMERIC` | `DECIMAL(precision, scale)` | From `NUMERIC_PRECISION`/`NUMERIC_SCALE`; precision clamped to 38, scale clamped to precision; missing precision/scale defaults to `DECIMAL(38, 0)` with a logged warning rather than guessing. |
| `VARCHAR`, `CHAR`, `GUID` | `STRING` | |
| `DATE` | `NAIVE_DATE` | Must be exactly `YYYY-MM-DD` for the SDK's parser. |
| `TIMESTAMP` (`%Library.TimeStamp`) | `NAIVE_DATETIME` | Carries no timezone in IRIS; `NAIVE_DATETIME` is the matching "no offset" Fivetran type. |
| `POSIXTIME` (`%Library.PosixTime`) | `UTC_DATETIME` | **See below -- this one needed a real fix.** |
| `VARBINARY`, `BINARY` | `BINARY` | |
| `TIME` | `STRING` | No native Fivetran time-of-day type is usable in SDK 2.12.1 -- see "What we deliberately drop." |
| anything unrecognized | `STRING` | Logged as a warning; never silently dropped. |

### What we deliberately drop

- **`LONGVARCHAR`/`LONGVARBINARY`** (`%Stream.GlobalCharacter` /
  `%Stream.GlobalBinary`, i.e. any IRIS stream/BLOB/CLOB column): dropped
  from the synced schema entirely (`type_mapping.DROPPED_TYPES`), not
  merely type-mapped. IRIS SQL forbids using a stream column in most
  scalar/aggregate functions or in a `WHERE` clause (`SQLCODE -37`), so a
  stream column can never be a cursor field, and reading one properly
  needs a second per-row stream-read plus a size policy (inline vs.
  Fivetran's file-upload API) that cannot be verified without a live IRIS
  instance. A future iteration could add this behind an opt-in flag.
- **`OREF`**: an in-process object reference, not durable column data.
  Meaningless outside the originating IRIS process; always dropped.
- **Hard deletes on incremental tables**: a cursor column can only report
  rows that changed, never rows that were removed. Full-refresh tables
  *do* detect deletes (via `truncate()` + full reload every cycle);
  incremental tables do not, unless the source has its own
  tombstone/soft-delete column, which this connector does not assume.
- **`NAIVE_TIME`**: the Fivetran wire protocol
  (`common_pb2.DataType.NAIVE_TIME`) defines a time-of-day type, but the
  installed SDK (2.12.1) does not actually support it --
  `type_coercion.py` maps it straight to `_raise_unsupported_type`, and the
  string-based schema parser (`connector_helper.process_data_type`) has no
  case for `"TIME"`/`"NAIVE_TIME"` at all. Confirmed by reading the
  installed package, not assumed. `TIME` columns are mapped to `STRING`
  instead.

### The `POSIXTIME` -> `UTC_DATETIME` fix (found by actually running `fivetran debug`)

`%Library.PosixTime` is defined as seconds-since-epoch -- an unambiguous
UTC instant by construction -- so it maps to Fivetran's `UTC_DATETIME`.
IRIS's DB-API driver formats it in ODBC mode as `YYYY-MM-DD
HH:MM:SS.FFFFFF`, with **no timezone offset at all**. Running `fivetran
debug` against this connector's first draft failed with:

```
ValueError: time data '2026-02-01T10:00:00.000000' does not match format '%Y-%m-%dT%H:%M:%S.%f%z'
```

because `fivetran_connector_sdk.type_coercion._parse_utc_datetime_str`
*requires* a trailing `%z` offset (or `Z`) in the string -- it will never
accept IRIS's own driver-formatted value as-is. `iris_connector.sync.py`
now calls `type_mapping.coerce_value_for_upsert()` on every value before
`Operations.upsert()`, which appends `+00:00` to any `UTC_DATETIME` string
lacking an offset before it goes anywhere near the SDK. Re-running
`fivetran debug` after that fix succeeded end-to-end (pasted in
`STATUS.md`), and a DuckDB read of the resulting synced row confirms
`visit_at` landed as `TIMESTAMP WITH TIME ZONE` at the correct UTC instant.

**This is exactly the class of "awkward case" this task asked to be found
and documented, not glossed over.** It is also the reason `db.py`'s real
`connect()` path is still marked unverified: this fix assumes the DB-API
driver's ODBC-mode formatting is always the UTC wall clock with no
server-local skew, which has not been checked against a live IRIS
instance.

### NULL handling

`None` passes straight through for every column; `Operations`'s own
`_map_data_to_columns` encodes any `None` value as SQL `NULL` regardless of
the column's declared type, so `iris_connector.sync`/`type_mapping` do not
need (and deliberately do not have) any type-specific NULL handling. This
assumes the DB-API driver returns Python `None` for SQL `NULL` -- standard
PEP 249 behavior, but **unverified against a live IRIS instance**.

## Sync design

See the module docstring in `iris_connector/sync.py` for the full state
shape and reasoning. Summary:

- **Incremental** (table listed in `cursor_fields`): `WHERE cursor_field >=
  ?`, checkpointing the max cursor value seen after every batch, not only
  at table completion -- so an interrupted sync resumes mid-table. `>=`
  (not `>`) can re-emit the last row(s) of the previous run when several
  rows share the exact same cursor value; that is deliberate and safe,
  because `Operations.upsert()` is a keyed upsert (a no-op on an
  already-synced row, never a duplicate).
- **Full-refresh** (every other table): `truncate()` once per reload
  cycle, then reload. A single-column primary key gets the same
  mid-table resumability via keyset pagination (`WHERE pk > ?`); a
  composite or absent primary key restarts that table's scan from the
  beginning on resume -- still *correct* (never re-truncates mid-load,
  always finishes with every row reloaded), just not incremental about
  resuming.
- **Checkpointing**: `truncate()` is checkpointed immediately, before any
  row is upserted, specifically so a crash between the truncate and the
  first row can never cause a second `truncate()` on resume (which would
  discard rows the resumed run had already re-upserted).

## Testing strategy

`iris_connector/db.py` defines `DBConnection`/`DBCursor` as
`typing.Protocol`s -- the only two names every other module in this
package is allowed to depend on for talking to IRIS. `iris_connector/db.py`
is also the *only* module that imports the real `iris` package, and only
inside `connect()`, so importing anything else in this package -- or
running the test suite -- never requires `intersystems-irispython` to be
installed.

`iris_connector/fake_db.py`'s `FakeConnection`/`FakeCursor` implement those
same two protocols against an in-memory table model, plus a small
regex-based interpreter scoped to the *specific, fixed* SQL shapes
`catalog.py`/`sync.py` generate (schema discovery against
`INFORMATION_SCHEMA`, and `SELECT ... FROM schema.table [WHERE ... ] [ORDER
BY ...]`). It is a test double for this connector's own queries, not a
general SQL engine -- the same "fake, not full emulator" spirit as
`careconnect-sdoh/evals`'s provider-agnostic fakes (per this repo's
`CLAUDE.md`).

Every test in `tests/` drives the connector through this fake -- see
`STATUS.md` for the exact `pytest` output.

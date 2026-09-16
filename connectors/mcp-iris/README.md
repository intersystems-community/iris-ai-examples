# mcp-iris

A reference [Model Context Protocol](https://modelcontextprotocol.io) server
for InterSystems IRIS, built on the official `mcp` PyPI package, stdio
transport. It exists to close the **directory-presence gap** described in
[`../../research/ecosystem-connector-gaps.md`](../../research/ecosystem-connector-gaps.md#2-ai-agent-connector-directories--the-fastest-moving-surface-in-2026):
IRIS already has working MCP servers (InterSystems's own AI Hub
`iris-mcp-server` and the community `caretdev/mcp-server-iris`), but neither
is listed in any AI agent connector directory.

**Read [`PUBLISHING.md`](./PUBLISHING.md) before submitting anything
anywhere** — its conclusion is that an InterSystems-owned submission should
almost certainly list the AI Hub server, not this one. This package's real
job is to (a) be a small, honestly-tested reference for what a good IRIS MCP
server's security boundary looks like, and (b) do the schema-validation
homework for the three directories named in the task, once, so whoever
submits either server doesn't have to re-derive it.

Read [`STATUS.md`](./STATUS.md) for exactly what was and wasn't verified —
there is no running IRIS instance or Docker daemon in the environment this
was built in, so nothing here has been integration-tested against a live
namespace.

## What's here

```
src/mcp_iris/
  sql_guard.py     Read-only SQL enforcement (the actual security boundary)
  identifiers.py   Strict allow-list validation for table/column/schema names
  db.py            DBConnection/DBCursor Protocol + QueryExecutor (row cap, timeout)
  catalog.py       SQL builders: list_schemas, list_tables, describe_table
  vector.py        SQL builder: IRIS native VECTOR_COSINE similarity search
  server.py        Wires the above onto mcp.server.mcpserver.MCPServer as 5 tools
  __main__.py      `python -m mcp_iris` stdio entrypoint (reads IRIS_* env vars)
tests/             96 tests, offline, no IRIS/Docker required
registry/
  mcp-registry/    MCP registry server.json + the schema it validates against
  claude-desktop-extension/  MCPB manifest.json (Claude Desktop Extension) + schema
  chatgpt/         Why there's no manifest here, and a submission-prep checklist instead
scripts/
  validate_server_json.py   Re-runs the server.json validation shown in STATUS.md
```

## Tools

| Tool | What it does |
| --- | --- |
| `list_schemas` | List every SQL schema in the connected namespace |
| `list_tables` | List tables/views, optionally filtered to one schema |
| `describe_table` | Column name, data type, nullability, ordinal position |
| `run_query` | Run a single **read-only** SQL statement |
| `vector_search` | Top-K cosine similarity search over a `VECTOR` column |

Every tool is annotated `readOnlyHint: true`, `destructiveHint: false` in its
MCP `ToolAnnotations` (see `tests/test_server.py::test_every_tool_is_annotated_read_only`).

## The security boundary: `run_query`

`run_query` is the one tool that accepts free-text SQL from an LLM agent, so
it is the actual attack surface. `sql_guard.assert_read_only()` rejects
anything that is not a single `SELECT`/`WITH ... SELECT` statement, and does
so *without* trusting a naive substring check. It is layered:

1. **Comment-adjacency check first.** A comment sitting directly against a
   word character with no whitespace (`IN/**/SERT`) is rejected outright,
   before any comment-stripping happens — so a later stripping pass can't be
   tricked into re-forming a keyword from two otherwise-innocuous halves.
2. **Single-statement enforcement** via `sqlparse.split()`, a real,
   quote/comment-aware SQL tokenizer — not `sql.split(";")`. This closes
   semicolon stacking (`SELECT 1; DROP TABLE x`) and comment-hidden trailing
   statements (`SELECT 1; -- \nDROP TABLE x`), while still allowing a
   semicolon that's actually inside a string literal.
3. **Comment-stripping + string/identifier-literal masking**, so a forbidden
   word inside a string literal (`WHERE msg = 'insert failed'`) is never
   mistaken for the keyword, and a forbidden word can't be smuggled inside a
   comment either (it's gone by the time keywords are scanned).
4. **Leading-keyword requirement**: the statement must start with `SELECT`
   or `WITH`.
5. **Whole-statement keyword scan** — not just the first token — for
   `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CALL`,
   `GRANT`, `REVOKE`, `CREATE`, `EXEC`/`EXECUTE`, `MERGE`, `INTO`, `SET`,
   `LOCK`, and a handful of other vendor-specific mutating keywords. Scanning
   the *whole* statement (not just the leading token) is what catches a
   **writable CTE** — `WITH x AS (INSERT INTO t ... ) SELECT * FROM x` still
   starts with the allowed `WITH`, but the `INSERT` inside it is caught.

`tests/test_sql_guard.py` has ~50 parametrized cases: legitimate queries that
must pass (including ones with `DROP`/`UPDATE`/`INSERT` etc. as literal
string content, or as a substring of a column name like `Updated_At`), and
adversarial ones that must fail (comment-splitting, multi-statement stacking,
case tricks, whitespace/tab tricks, writable CTEs, `SELECT ... INTO`,
leading-noise statement smuggling).

Table/column/schema names used by `describe_table`, `list_tables`, and
`vector_search` are **never** string-interpolated without going through
`identifiers.validate_identifier()` first — an allow-list regex
(`^[A-Za-z_][A-Za-z0-9_]*$`), not an escaping scheme. That closes the second
injection surface DB-API parameter placeholders can't cover (you can bind a
`?` to a value, but not to an identifier).

### Row cap and query timeout

- **Row cap** (`QueryExecutor`, default 1000, overridable per-call): the
  executor calls `cursor.fetchmany(cap + 1)`, never `fetchall()`, and
  truncates to `cap` with `truncated: true` in the response if more rows
  existed. This bounds how much this process ever materializes, though it
  cannot stop IRIS from having scanned a huge table server-side before
  returning the first rows — a caveat worth knowing, not a bug.
- **Query timeout** (default 30s, overridable per-call): `cursor.execute()`
  runs in a worker thread; `future.result(timeout=...)` bounds how long
  `run_query` waits. **Known limitation, documented rather than hidden:**
  PEP 249 has no standard query-cancellation API, and the IRIS Python DB-API
  does not expose one either, so timing out here means this process stops
  waiting and closes its connection — it does not guarantee IRIS itself
  stopped executing the query. See `QueryTimeoutError`'s docstring in `db.py`.

## Testability: everything is driven off a `Protocol`, not a live IRIS

`db.DBConnection`/`db.DBCursor` are `typing.Protocol`s describing the tiny
slice of PEP 249 the tools need. `tests/conftest.py`'s `FakeConnection`/
`FakeCursor` implement that Protocol entirely in memory — including
simulating a slow query for the timeout test — so all 96 tests run with **no
IRIS instance, no Docker daemon, no network**, the same offline model as
`careconnect-sdoh/evals`. The only place the real `iris` package is imported
is `IRISConnectionFactory.__call__` in `db.py`, and that import is deferred
to call time so importing the rest of the package never requires the IRIS
driver to be installed at all.

## Running the tests

```bash
cd connectors/mcp-iris
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,iris]"
pytest tests/ -v
```

The `iris` extra (`intersystems-irispython`) is only needed to *run* the
server against a real IRIS instance; the test suite does not need it. Full,
real output from a clean install and test run is in `STATUS.md`.

## Running the server against a real IRIS instance

Not exercised in this environment (no IRIS, no Docker — see `STATUS.md`).
The intended shape, per
[InterSystems's own DB-API docs](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=BPYDBAPI_about):

```bash
export IRIS_HOSTNAME=localhost
export IRIS_PORT=1972          # default
export IRIS_NAMESPACE=USER     # default
export IRIS_USERNAME=_SYSTEM   # default -- use a read-only account instead for anything real
export IRIS_PASSWORD=SYS
export MCP_IRIS_ROW_CAP=1000            # default
export MCP_IRIS_QUERY_TIMEOUT_SECONDS=30 # default

python -m mcp_iris
```

`sql_guard` and the row cap/timeout are defense in depth, not a substitute
for connecting as a database role that genuinely lacks write privileges —
use one if your IRIS deployment supports role-based SQL privileges (see
[Defining Tables | Using SQL](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GSQL_tables)
for IRIS's privilege model).

## Connecting from an MCP client

Any stdio MCP client can run this with `python -m mcp_iris` and the
environment variables above. For Claude Desktop specifically, see
`registry/claude-desktop-extension/manifest.json`, which declares the same
variables as `user_config` fields the desktop app collects through its UI
instead of a shell environment.

## IRIS SQL facts this server relies on

Verified where noted; not independently confirmed against a live namespace
in this environment (see `STATUS.md`):

| Fact | Source |
| --- | --- |
| `import iris; iris.connect(hostname=, port=, namespace=, username=, password=)` returns a PEP-249-shaped connection | [Introduction to Python DB-API for InterSystems IRIS](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=BPYDBAPI_about) |
| `INFORMATION_SCHEMA.COLUMNS.COLUMN_NAME` / `.TABLE_NAME` exist and are queryable | [`INFORMATION.SCHEMA.COLUMNS` class reference](https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=INFORMATION.SCHEMA.COLUMNS), which shows `SELECT COLUMN_NAME, AUTO_INCREMENT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'MyTable'` as a worked example |
| `INFORMATION_SCHEMA.TABLES` returns one row per table the current user can see | [`INFORMATION.SCHEMA.TABLES` class reference](https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=INFORMATION.SCHEMA.TABLES) |
| `INFORMATION_SCHEMA.SCHEMATA`, and the remaining ANSI column names used here (`TABLE_SCHEMA`, `TABLE_TYPE`, `DATA_TYPE`, `IS_NULLABLE`, `ORDINAL_POSITION`, `COLUMN_DEFAULT`) | Inferred from the same `INFORMATION.SCHEMA.*` naming pattern as the two confirmed views above; **not independently confirmed** — see `catalog.py`'s module docstring and `STATUS.md` |
| `VECTOR_COSINE(col, TO_VECTOR(?, DOUBLE))` pattern | Already used elsewhere in this repo — `AGENTS.md`'s "Vector Search SQL Pattern" section, `kg-ticket-resolver/` |

## What's deliberately not here

- **No general SQL parser.** `sql_guard` is a security boundary for one
  specific job (allow read-only, reject everything else), not a SQL engine.
- **No `packages`/`remotes` entry in `registry/mcp-registry/server.json`.**
  This package is not published to PyPI (or anywhere else) from this
  session — see that file's `_meta` note and `PUBLISHING.md`.
- **No packaged `.mcpb` bundle**, only the `manifest.json` that would go
  inside one (validated with the real `mcpb` CLI — see `STATUS.md`).
- **No ChatGPT manifest file** — there isn't one to write; see
  `registry/chatgpt/README.md`.

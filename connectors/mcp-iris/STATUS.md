# STATUS

## VERIFIED

**Clean install, from PyPI, in a fresh venv, just now (no prior cache reused
for the report below — this is a brand-new `/tmp/mcp_iris_clean_venv`):**

```
$ python3 -m venv /tmp/mcp_iris_clean_venv
$ /tmp/mcp_iris_clean_venv/bin/pip install -e ".[dev,iris]"
...
Successfully installed annotated-types-0.8.0 anyio-4.15.1 attrs-26.1.0 cffi-2.1.1
click-8.5.0 cryptography-50.0.1 h11-0.16.0 httpcore2-2.13.0 httpx2-2.13.0 idna-3.19
iniconfig-2.3.0 intersystems-irispython-5.4.0 jsonschema-4.26.0
jsonschema-specifications-2025.9.1 mcp-2.2.0 mcp-iris-0.1.0 mcp-types-2.2.0
opentelemetry-api-1.44.0 packaging-26.3 pluggy-1.6.0 pycparser-3.0 pydantic-2.13.5
pydantic-core-2.46.5 pygments-2.21.0 pyjwt-2.14.0 pytest-9.1.1 python-multipart-0.0.32
referencing-0.37.0 rpds-py-2026.6.3 sqlparse-0.5.5 sse-starlette-3.4.11
starlette-1.6.0 truststore-0.10.4 typing-extensions-4.16.0 typing-inspection-0.4.4
uvicorn-0.53.0
```

Python 3.11.15. `pip install -e ".[dev,iris]"` installs cleanly, including
the `iris` extra (`intersystems-irispython`), with zero errors — the `mcp`
PyPI package the task asked for is real, installs, and this session used
its actual API (not a hallucinated one; `mcp` 2.2.0's `MCPServer` class,
`@server.tool(...)` decorator, `ToolAnnotations`, and `server.run("stdio")`
were all confirmed by importing and introspecting the installed package
before writing `server.py`).

**Note on the system Python:** importing `mcp` under this sandbox's
system-wide `python3` fails (`ModuleNotFoundError: No module named
'_cffi_backend'`, then a Rust/PyO3 panic from a conflicting system
`cryptography` build) — a pre-existing environment conflict between the
apt-installed `cryptography` and the one `mcp`'s dependency chain
(`pyjwt[crypto]` → `cryptography` → `cffi`) needs. **A clean venv (as above)
does not have this problem** and is what every command in this document
actually used. Anyone running this for real should use a venv, not the
system interpreter, for the same reason.

**All 96 tests pass, on the exact interpreter and installed packages
above, just now:**

```
$ /tmp/mcp_iris_clean_venv/bin/python -m pytest tests/ -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
plugins: anyio-4.15.1
collecting ... collected 96 items

tests/test_catalog.py .......... [10 tests]
tests/test_db.py .......... [11 tests]
tests/test_main_entrypoint.py ..... [5 tests]
tests/test_server.py ......... [9 tests]
tests/test_sql_guard.py ..................................................... [53 tests]
tests/test_vector.py ........ [8 tests]

============================== 96 passed in 1.09s ==============================
```

(Full per-test names were shown with `-v`; abbreviated here for length —
every one of the 96 passed, none skipped, none xfailed. Re-run yourself with
`pytest tests/ -v` for the complete list.)

This covers, entirely offline (no IRIS, no Docker, no network — the
`tests/conftest.py` `FakeConnection`/`FakeCursor` satisfy the same
`db.DBConnection`/`db.DBCursor` `Protocol` the real IRIS adapter does):

- **`sql_guard.assert_read_only`** (53 parametrized cases): every query in
  the task's explicit reject list (INSERT/UPDATE/DELETE/DROP/ALTER/
  TRUNCATE/CALL/GRANT), plus REVOKE/CREATE/EXEC/EXECUTE/MERGE; multi-
  statement stacking via semicolon (plain, comment-hidden, leading-noise
  variants); comment-splitting a keyword in two (`IN/**/SERT`); case tricks
  (`InSeRt`, `dRoP`); whitespace/tab/newline tricks; a writable CTE
  (`WITH x AS (INSERT ...) SELECT * FROM x`); `SELECT ... INTO`; and that
  legitimate queries containing forbidden words as *string-literal content*
  or as a *substring of a column name* (`Updated_At`) are correctly
  **allowed**, not false-positived.
- **`db.QueryExecutor`**: row cap enforcement and non-truncation when the
  result fits, including a per-call override; the read-only guard running
  *before* any connection is opened (asserted via a factory that records
  whether it was ever called); the connection being closed on both success
  and timeout; and — the one that actually proves the timeout works, not
  just that it's wired — `test_run_query_times_out_on_slow_query` asserts
  wall-clock elapsed time is `< 1.0s` against a fake query that sleeps 2s
  with a 0.1s timeout configured. (This test caught a real bug during
  development: an earlier version used `with ThreadPoolExecutor() as pool`,
  whose `__exit__` calls `shutdown(wait=True)` and therefore blocks until
  the slow call finishes regardless of the timeout, defeating it entirely.
  Fixed by calling `shutdown(wait=False)` on the timeout path instead — see
  `db.py`'s `_execute_with_timeout` docstring/comment for the explanation
  left in place.)
- **`identifiers.validate_identifier`/`validate_qualified_name`**: reject
  attempts to smuggle SQL through a table/column/schema-name argument
  (`"Sample; DROP TABLE Foo"`, `"Sample'--"`, empty strings).
- **`catalog.py`**: schema/table names are always bound as `?` parameters,
  never string-interpolated (asserted directly: `"Sample" not in sql`).
- **`vector.py`**: builder output matches the `VECTOR_COSINE(...,
  TO_VECTOR(?, DOUBLE))` pattern, is itself still accepted by
  `sql_guard.assert_read_only` (defense in depth), rejects bad
  table/column identifiers and non-numeric/empty/oversized vectors.
- **`server.py`** (via `MCPServer.call_tool`/`list_tools` against a fake
  connection): all 5 tools are registered with the expected names; every
  tool's `ToolAnnotations.read_only_hint is True` and `destructive_hint is
  False`; a rejected write statement or bad identifier surfaces as a raised
  `ToolError` (confirmed by reading `mcp.server.mcpserver.tools.base`/
  `.server` in the installed `mcp` 2.2.0 package: `MCPServer.call_tool()`
  raises `ToolError` for a deliberate rejection, and the SDK's own
  lower-level JSON-RPC request handler — also read in that same package —
  is what converts exactly that exception into
  `CallToolResult(is_error=True, ...)` for a real MCP client; that
  conversion path itself is the SDK's own tested code and wasn't
  re-exercised here).
- **`__main__.py`**: requires `IRIS_HOSTNAME` (exits 2 with a clear message
  if unset — reproduced live, see below), env-var parsing defaults/
  overrides, and that `main()` calls `server.run("stdio")`.

**Reproduced live, just now, outside pytest, as an extra sanity check:**

```
$ python -m py_compile src/mcp_iris/*.py && echo "COMPILE OK"
COMPILE OK
$ env -u IRIS_HOSTNAME python -m mcp_iris; echo "exit code: $?"
mcp_iris: IRIS_HOSTNAME environment variable is required (see README.md for the full list of IRIS_* variables)
exit code: 2
```

**`registry/mcp-registry/server.json` validates against the real, fetched
MCP registry JSON Schema**, using the real `jsonschema` PyPI package:

```
$ python scripts/validate_server_json.py
OK: registry/mcp-registry/server.json conforms to server.schema.json
    (schema $id: https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json)
```

The schema file (`registry/mcp-registry/server.schema.json`) is a
byte-for-byte copy of `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`,
fetched read-only via `curl` in this session (HTTP 200). That exact
dated URL is the `$schema` value used in the registry's own current
documentation examples
(`docs/reference/server-json/generic-server-json.md`, fetched from
`raw.githubusercontent.com/modelcontextprotocol/registry/main/...`, HTTP
200) — not a URL invented for this task. `registry/mcp-registry/server.json`
has no `packages`/`remotes` entry, by design (see that file's own `_meta`
note and `PUBLISHING.md`): the schema's only *required* fields are `name`,
`description`, `version`, confirmed by reading
`definitions.ServerDetail.required` in the fetched schema itself.

**`registry/claude-desktop-extension/manifest.json` validates against the
real MCPB manifest schema, using the real, official `mcpb` CLI** (not a
hand-rolled check):

```
$ npm install @anthropic-ai/mcpb   # installed 55 packages, version 2.1.2
$ node node_modules/@anthropic-ai/mcpb/dist/cli/cli.js validate \
    registry/claude-desktop-extension/manifest.json
Manifest schema validation passes!
```

The schema file copied alongside it
(`registry/claude-desktop-extension/mcpb-manifest-v0.4.schema.json`) is the
one that ships **inside** the official `@anthropic-ai/mcpb` npm package
(`schemas/mcpb-manifest-v0.4.schema.json` in the 2.1.2 tarball fetched from
`registry.npmjs.org`, HTTP 200) — the CLI resolves which schema file to use
from the manifest's own declared `manifest_version` (confirmed by reading
`dist/node/validate.js`'s use of `getManifestVersionFromRawData` /
`MANIFEST_SCHEMAS` in the installed package), so this is the actual schema
the actual tool validates against, not a guess at what "the DXT schema"
might be. The plain-English field reference at
`https://raw.githubusercontent.com/anthropics/mcpb/main/MANIFEST.md`
(HTTP 200, fetched in this session) was used to write the manifest's
content; the JSON Schema inside the npm package is what actually checked
it.

**No JSON Schema exists for a ChatGPT/Apps SDK connector submission** —
confirmed by search against `developers.openai.com/apps-sdk/*` and
`.../plugins/deploy/*` (search snippets only; the domain itself returned
`EGRESS_BLOCKED` when fetched directly with `WebFetch` in this session — see
UNVERIFIED). `registry/chatgpt/submission_prep.json` is explicitly labeled
as not schema-validated for this reason; nothing in this repo claims
otherwise.

**IRIS connectivity facts used in the code**, confirmed against
`docs.intersystems.com` pages via search snippets (the domain returned
`EGRESS_BLOCKED` for direct `WebFetch` in this session, same as the other
InterSystems/Anthropic/OpenAI docs domains — see UNVERIFIED):
- `import iris; iris.connect(hostname=, port=, namespace=, username=,
  password=)` — from "Introduction to Python DB-API for InterSystems IRIS."
- `INFORMATION_SCHEMA.COLUMNS.COLUMN_NAME` and `.TABLE_NAME` exist and are
  queryable — from the `INFORMATION.SCHEMA.COLUMNS` class reference page,
  which shows a worked example query using exactly those column names.
- `INFORMATION_SCHEMA.TABLES` returns one row per visible table — from the
  `INFORMATION.SCHEMA.TABLES` class reference page.

## UNVERIFIED

- **`INFORMATION_SCHEMA.SCHEMATA`, and the remaining ANSI column names**
  (`TABLE_SCHEMA`, `TABLE_TYPE`, `DATA_TYPE`, `IS_NULLABLE`,
  `ORDINAL_POSITION`, `COLUMN_DEFAULT`) used in `catalog.py`. Only
  `INFORMATION_SCHEMA.COLUMNS.COLUMN_NAME`/`.TABLE_NAME` and
  `INFORMATION_SCHEMA.TABLES`'s existence were directly confirmed (see
  VERIFIED). The rest follow the same `INFORMATION.SCHEMA.*` class-naming
  pattern as ANSI-standard views, and IRIS documents itself as supporting
  `INFORMATION_SCHEMA`, but this session never ran a query against a real
  IRIS namespace to confirm the exact column set. **This is the single
  biggest correctness risk in the catalog tools** — see HUMAN ACTIONS.
- **`sql_guard`'s SELECT/WITH detection and forbidden-keyword list against
  IRIS's actual SQL grammar**, specifically any IRIS-specific syntax
  (e.g. IRIS's own extensions or embedded-SQL host-variable syntax) that
  might not be valid ANSI/T-SQL-shaped SQL and therefore wasn't considered.
  The guard was tested against `sqlparse`'s tokenizer (generic SQL, not
  IRIS-aware) and against the adversarial cases the task named — not
  against IRIS's own SQL parser, because none is available in this
  environment.
- **`IRISConnectionFactory`/`iris.connect(...)` actually connecting to and
  querying a real IRIS instance.** `import iris` from
  `intersystems-irispython==5.4.0` succeeds (confirmed — see VERIFIED), and
  the call shape matches the documented API, but no query has ever actually
  run against live IRIS in this session: **there is no IRIS instance and no
  Docker daemon in this environment**, per the task's own stated hard
  limits.
- **The query-timeout's real-world effect on IRIS server-side state.**
  `QueryTimeoutError`'s docstring already says this plainly: PEP 249 has no
  standard cancellation API and the IRIS DB-API doesn't expose one, so a
  timeout here stops *this process* waiting, but doesn't confirm IRIS
  itself stopped executing. Untestable without a live instance to observe.
- **Direct fetches of `docs.intersystems.com`, `claude.com`, and
  `developers.openai.com`.** All three returned `EGRESS_BLOCKED` from this
  sandbox's network policy when fetched directly via `WebFetch`
  mid-session (`curl`'s own proxy-status check separately showed
  `docs.snowflake.com`, `learn.microsoft.com`, `docs.databricks.com`, and
  `www.databricks.com` also rejected at the proxy level — a sandbox-wide
  policy, not something specific to this task). Every claim sourced from
  those three domains above is from **WebSearch result snippets**, not a
  full page fetch, and is labeled that way inline. The MCP registry docs
  (`raw.githubusercontent.com/modelcontextprotocol/registry/...`) and the
  schema/npm hosts (`static.modelcontextprotocol.io`, `registry.npmjs.org`)
  *were* directly fetchable and fully read — those claims are on firmer
  ground than the three blocked domains.
- **Whether AI Hub's `iris-mcp-server` currently speaks Streamable HTTP**
  (required by the Claude Connectors Directory; SSE is stated to no longer
  be accepted) or only stdio/SSE. `PUBLISHING.md` flags this as something
  the AI Hub team needs to confirm — this session has no IRIS 2026.x
  instance to check against.
- **Whether `mcpb pack`-ing this reference server into an actual `.mcpb`
  bundle would succeed end-to-end** (icon requirements, `.mcpbignore`
  handling, etc.) — only `mcpb validate` on the manifest was run;
  `mcpb pack` was not attempted, since no packaged bundle was requested.

## HUMAN ACTIONS REQUIRED

1. **Confirm `INFORMATION_SCHEMA.SCHEMATA` and the ANSI column names in
   `catalog.py`** against a real IRIS namespace's `INFORMATION_SCHEMA`
   output before trusting `list_schemas`/`list_tables`/`describe_table`
   against production data. This is the top correctness risk in the whole
   package, precisely because it could not be checked here.
2. **Decide AI Hub's actual distribution/namespace story** for the MCP
   registry entry (real `packages` or `remotes` value, and which GitHub
   org/domain authenticates the `io.github.…`/`com.intersystems/…`
   namespace) — a product/ownership decision, not something this session
   can resolve from a demo repo.
3. **Confirm whether AI Hub's `iris-mcp-server` speaks Streamable HTTP**
   (Claude Connectors Directory and ChatGPT's Apps SDK both require a
   public HTTP(S) endpoint; SSE is explicitly no longer accepted by
   Claude's directory) — needs a live IRIS 2026.x instance to check.
4. **Get InterSystems organizational credentials in front of each
   directory**: a GitHub org login or DNS TXT record for the MCP registry
   namespace; a Team/Enterprise Claude.ai org with Directory permission for
   the Connectors Directory; an OpenAI developer-org account with "Apps
   Management: Write" for ChatGPT. None of these exist in this session, on
   purpose — the task's hard rules forbid registering with or authenticating
   against any of them here.
5. **Stand up a public HTTPS endpoint and complete domain verification**
   for whichever server is actually submitted to the Connectors Directory
   or ChatGPT — both directories gate on this, and it requires a real
   deployment and DNS control this session does not have.
6. **Publish a privacy policy URL** — both Claude's Connectors Directory
   and the desktop-extension form are documented to reject submissions
   missing one.
7. **Run the full test suite against a live IRIS instance** (any edition
   with SQL support) at least once before relying on this reference
   implementation for anything beyond its own offline tests — nothing here
   has ever executed against real IRIS.

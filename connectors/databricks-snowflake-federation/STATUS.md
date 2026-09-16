<!-- markdownlint-disable MD013 MD060 -->

# STATUS — databricks-snowflake-federation

Read this before trusting any claim in `README.md`. Three sections, as required:
VERIFIED (backed by pasted real command output), UNVERIFIED (everything requiring a
real workspace/account/instance — kept complete rather than convenient), and HUMAN
ACTIONS REQUIRED.

Ceiling on this task, same as every subdirectory under `connectors/` per
[`../README.md`](../README.md): **no running IRIS, no Docker daemon, no Databricks
workspace, no Snowflake account.** Additionally, and specific to this task: **this
session's network egress policy blocked direct HTTP access to
`docs.databricks.com`, `docs.snowflake.com`, `learn.microsoft.com`, and
`docs.intersystems.com`** — confirmed below. Nothing here has been run against a real
warehouse, cluster, or IRIS instance.

---

## VERIFIED

Claims backed by real, pasted command output, run in this session.

### 1. All 57 offline unit tests pass, in a fresh virtualenv with only `requirements.txt` installed

```
$ python3 -m venv /tmp/ddlfed-venv
$ /tmp/ddlfed-venv/bin/pip install -r requirements.txt
Collecting pytest<10,>=8.0 (from -r requirements.txt (line 5))
  Using cached pytest-9.1.1-py3-none-any.whl.metadata (7.6 kB)
Collecting iniconfig>=1.0.1 (from pytest<10,>=8.0->-r requirements.txt (line 5))
  Using cached iniconfig-2.3.0-py3-none-any.whl.metadata (2.5 kB)
Collecting packaging>=22 (from pytest<10,>=8.0->-r requirements.txt (line 5))
  Using cached packaging-26.3-py3-none-any.whl.metadata (3.5 kB)
Collecting pluggy<2,>=1.5 (from pytest<10,>=8.0->-r requirements.txt (line 5))
  Using cached pluggy-1.6.0-py3-none-any.whl.metadata (4.8 kB)
Collecting pygments>=2.7.2 (from pytest<10,>=8.0->-r requirements.txt (line 5))
  Using cached pygments-2.21.0-py3-none-any.whl.metadata (2.5 kB)
Successfully installed iniconfig-2.3.0 packaging-26.3 pluggy-1.6.0 pygments-2.21.0 pytest-9.1.1

$ /tmp/ddlfed-venv/bin/python -m pytest tests/
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/iris-ai-examples/connectors/databricks-snowflake-federation
collected 57 items

tests/test_databricks_ddl.py ............                                [ 21%]
tests/test_partitioning.py ..........                                    [ 38%]
tests/test_shared_iris_jdbc.py ................                          [ 66%]
tests/test_snowflake_ddl.py ...........                                  [ 85%]
tests/test_snowpark_ingest.py ...                                        [ 91%]
tests/test_spark_read_options.py .....                                   [100%]

============================== 57 passed in 0.05s ==============================
```
This is the exact, unedited terminal output from the venv run. The same 57 tests were
also run with `-v` (full per-test names, all `PASSED`) in the ambient environment
before this venv was created; both runs are `57 passed`, zero failures, zero skips.

This covers: JDBC URL / pgwire DSN construction and input validation, SQL-literal
escaping, the Databricks `CREATE CONNECTION`/`CREATE FOREIGN CATALOG` DDL shape and
its documented default allow-list / forbidden-options rules, an offline grammar
validator for both Databricks DDL statements and all three Snowflake DDL statements,
Spark JDBC partition-plan arithmetic, and that generated code snippets never embed a
literal password.

### 2. All modules import and compile cleanly

```
$ python3 -m py_compile shared/iris_jdbc.py shared/partitioning.py databricks/ddl.py \
    databricks/spark_read_options.py snowflake/ddl.py snowflake/snowpark_ingest.py conftest.py
compile OK
$ python3 -c "import ast; ast.parse(open('databricks/spark_read_iris_notebook.py').read())"
databricks/spark_read_iris_notebook.py OK syntax
```

### 3. `snowflake`/`databricks` are not installed as real packages in this environment

```
$ pip show snowflake-connector-python databricks-connect snowflake databricks
WARNING: Package(s) not found: databricks, databricks-connect, snowflake, snowflake-connector-python
```
So this directory's local `snowflake/` and `databricks/` recipe packages do not
currently shadow anything real here — see the naming caveat in `conftest.py` for what
that would mean if it ever did.

### 4. `docs.databricks.com`, `docs.snowflake.com`, `learn.microsoft.com`, and
   `docs.intersystems.com` are unreachable in this session (network policy, not a
   research failure)

```
$ curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://docs.databricks.com/aws/en/query-federation/jdbc-connection
curl: (56) CONNECT tunnel failed, response 403
HTTP 000

$ curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://docs.snowflake.com/en/user-guide/data-integration/openflow/about
curl: (56) CONNECT tunnel failed, response 403

$ curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://docs.intersystems.com
curl: (56) CONNECT tunnel failed, response 403
```
The WebFetch tool independently reported `EGRESS_BLOCKED` for the same three domains.
**Consequence**: every Databricks-doc and Snowflake-doc claim in `README.md` is
sourced through the WebSearch tool's synthesis of indexed content (each with the doc
URL cited), not a direct, verbatim fetch of the page. GitHub (`raw.githubusercontent.com`)
and PyPI were reachable directly, so every `iris-pgwire` claim in `README.md` **was**
fetched directly and is quoted/paraphrased from the real file, not synthesized.

### 5. `iris-pgwire` primary-source claims, fetched directly from GitHub

```
$ curl -sS https://raw.githubusercontent.com/intersystems-community/iris-pgwire/main/README.md
$ curl -sS https://raw.githubusercontent.com/intersystems-community/iris-pgwire/main/docs/BI_TOOLS.md
$ curl -sS https://raw.githubusercontent.com/intersystems-community/iris-pgwire/main/docs/PG_CATALOG.md
$ curl -sS https://raw.githubusercontent.com/intersystems-community/iris-pgwire/main/KNOWN_LIMITATIONS.md
```
All four returned real file content (HTTP 200, content inline in this session's
transcript). Facts pulled from them and cited in `README.md`: verified client list
including "Java: PostgreSQL JDBC"; 6-table partial `pg_catalog` emulation translated
from `INFORMATION_SCHEMA`; `pgAdmin`/`Metabase` rated "Partial" catalog compatibility;
no native TLS; 5-connection cap on IRIS Community Edition.

---

## UNVERIFIED

Everything below requires a real Databricks workspace, a real Snowflake account, a
running IRIS instance, or a Docker daemon that this task does not have. Kept
complete rather than convenient.

### Databricks (Path A)

- The `CREATE CONNECTION ... TYPE JDBC` and `CREATE FOREIGN CATALOG` DDL in
  `databricks/ddl.py` has **never been run** against a real Databricks SQL warehouse
  or Unity Catalog metastore. The offline grammar validator only checks structural
  shape (keyword order, required clauses, quote balance) against the documented
  grammar as reconstructed from WebSearch results — it is not a real SQL parser and
  cannot catch every way real Databricks SQL could reject the statement (e.g. a
  privilege error, a volume-path-not-found error, an unsupported option combination).
- Whether the IRIS JDBC driver (`com.intersystems.jdbc.IRISDriver`) actually behaves
  correctly when loaded into Databricks' JDBC-connection sandbox has not been tested
  — the sandboxing/classloading Databricks documents for bring-your-own drivers is
  untested against this specific driver.
- Whether `spark.read.format("jdbc")` against IRIS actually produces `PushedFilters`
  in `.explain()` (i.e., whether Spark's JDBC dialect inference works acceptably for
  IRIS's SQL dialect, given IRIS is not one Spark ships a built-in `JdbcDialect`
  for) is unverified. It may fall back to Spark's generic ANSI-SQL dialect, which
  would still push simple filters but could mishandle IRIS-specific types/functions.
- Actual query latency/throughput, connection-pool behavior under
  `numPartitions > 1` concurrent JDBC connections against IRIS, and whether IRIS's
  connection limits (e.g. Community Edition's low connection cap, per `iris-pgwire`'s
  own README) become the bottleneck — all unverified, no live IRIS to load-test
  against.
- **The `iris-pgwire` + native-PostgreSQL-connector path for Databricks is entirely
  unverified as a *Databricks* integration.** `iris-pgwire`'s own test suite (171/171
  tests, 92% coverage per its README) verifies pgwire against a real IRIS instance and
  against direct PostgreSQL client libraries — it has never been pointed at from
  inside a Databricks Lakehouse Federation PostgreSQL connection. Whether Databricks'
  specific catalog-introspection queries (which may go beyond the 6 tables pgwire
  emulates) succeed is a real open question, not just a caveat.

### Snowflake (Path B)

- The `CREATE NETWORK RULE` / `CREATE SECRET` / `CREATE EXTERNAL ACCESS INTEGRATION`
  DDL in `snowflake/ddl.py` has never been run against a real Snowflake account.
  Same caveat as Databricks: the offline grammar validator checks structural shape
  only.
- `session.read.dbapi(...)` against `psycopg2` connected through `iris-pgwire` has
  never been executed — no Snowflake account, no running IRIS+pgwire container.
  Whether Snowpark's DB-API integration handles pgwire's partial `pg_catalog`/type
  mapping correctly (e.g. IRIS-specific numeric/date types as translated through
  pgwire's PostgreSQL wire encoding) is unverified.
- The Snowpark JDBC fallback (`session.read.jdbc(...)`) has likewise never been
  executed, and it is explicitly a *public preview* Snowflake feature as of this
  research — its exact behavior, limits, and stability are Snowflake's to define and
  could change before GA.
- Cost/performance of either Snowpark path at real data volumes (a Java UDTF /
  parallel DBAPI read per Snowflake's own description) against a real IRIS instance:
  unverified.
- Whether `_snowflake.get_generic_secret_string` works exactly as rendered in
  `snowpark_ingest.py`'s generated code (parameter name, return shape) has not been
  executed inside an actual Snowflake stored procedure runtime.

### Both paths

- No end-to-end run exists anywhere in this deliverable. Every DDL statement, every
  Python snippet, and every partition plan is validated **offline only**: unit tests
  check the builders that produce these artifacts, not the artifacts' effect on a
  real system.
- Direct fetches of `docs.databricks.com`, `docs.snowflake.com`, and
  `docs.intersystems.com` were blocked by this session's egress policy (see VERIFIED
  #4). Every doc-grammar fact in `README.md` for those three domains is a
  WebSearch-tool synthesis of indexed content, cited by URL — not a verbatim
  primary-source quote pulled by this session. A human with unrestricted access
  should re-verify the exact DDL grammar against the live docs before running it
  against a production workspace.

---

## HUMAN ACTIONS REQUIRED

1. **Re-verify the exact DDL grammar directly against live docs** before running
   anything in `databricks/ddl.py` or `snowflake/ddl.py` against a real workspace —
   this session could not fetch `docs.databricks.com` / `docs.snowflake.com` directly
   (see VERIFIED #4), so every syntax claim rests on WebSearch synthesis, not a
   verbatim doc fetch.
2. **Stand up a real proof-of-concept**: an IRIS instance reachable from a Databricks
   workspace (JDBC path) and, separately, from a Snowflake account via External
   Access Integration (pgwire/DB-API path). Confirm the DDL actually runs, confirm
   `PushedFilters` appears in a Spark `.explain()`, confirm `session.read.dbapi`
   actually loads rows through pgwire. None of this can happen without credentials
   and infrastructure this task does not have.
3. **Get `intersystems-jdbc` and `iris-pgwire` onto a path a Databricks/Snowflake
   admin can actually install** — a Unity Catalog volume upload of the driver JAR,
   and/or a supported, TLS-terminated, connection-pooled deployment of `iris-pgwire`
   (it explicitly recommends nginx/HAProxy in front and has no native TLS — see
   VERIFIED #5). This is infrastructure work, not something this repo can ship.
4. **The partnership/field motion — this is the actual point of gap #3.** Per
   `../../research/ecosystem-connector-gaps.md`: "treat this as a partnership/field
   motion, not an engineering one. Target getting IRIS named in a Databricks
   custom-connector or JDBC-federation doc via a joint healthcare customer." Concretely:
   - Identify a joint InterSystems/Databricks (or InterSystems/Snowflake) healthcare
     customer already running both platforms.
   - Package this recipe (once proof-of-concepted per #2) as a joint reference
     architecture / solution brief co-branded with that customer.
   - Route it through InterSystems' partnership/alliances team to Databricks' and
     Snowflake's partner-engineering teams, whose documented pattern for adding a
     non-native source example to public docs is almost always "a customer or partner
     asked for this and we wrote it up" — not an unsolicited PR to their docs repo.
   - This step requires business-development access, an existing/willing joint
     customer, and vendor partner-program relationships that do not exist in this
     coding session. It is the highest-value action on this entire list and the one
     that most needs a human, not an agent.
5. **Decide this directory's permanent home.** Per `../README.md`, this is staged
   work — a connectors repo, docs contribution, or partner-engineering deliverable is
   a different kind of artifact than an `iris-ai-examples` demo. Nothing here should
   be treated as final placement until a maintainer decides.

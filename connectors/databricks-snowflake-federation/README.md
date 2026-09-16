<!-- markdownlint-disable MD013 MD060 -->

# Databricks / Snowflake federation recipes for InterSystems IRIS

Gap #3 from [`../../research/ecosystem-connector-gaps.md`](../../research/ecosystem-connector-gaps.md):
Databricks Lakehouse Federation names MySQL, PostgreSQL, Redshift, Snowflake, SQL
Server, Synapse, BigQuery, and Teradata. Lakeflow Connect adds Oracle, Salesforce,
Workday, Kafka. IRIS is on neither list, and Snowflake has no equivalent
bring-your-own-federation mechanism at all. Neither vendor will build an IRIS
connector. Both leave a documented back door. This directory is the reproducible,
InterSystems-owned recipe for using it — the code and tests here, the field motion
to get IRIS *named* in either vendor's docs is a human/partnership task (see
[`STATUS.md`](STATUS.md)).

**Read [`STATUS.md`](STATUS.md) before trusting any claim below** — it separates what
is backed by pasted real command output from what is necessarily unverified (no
Databricks workspace, no Snowflake account, no running IRIS, no Docker daemon exist
in this environment).

**Placement/isolation**: this directory follows [`../README.md`](../README.md). It
writes nothing outside itself, imports nothing from the three example apps in this
repo, and nothing in those apps imports from it.

## Layout

```
shared/iris_jdbc.py          IRIS JDBC URL / pgwire DSN / identifier validation (both paths use this)
shared/partitioning.py       Spark JDBC partition-plan math (path A)
databricks/ddl.py            CREATE CONNECTION / CREATE FOREIGN CATALOG builder + offline grammar check
databricks/spark_read_options.py   spark.read.format("jdbc") options builder
databricks/spark_read_iris_notebook.py   annotated recipe notebook (illustrative, not executed)
snowflake/ddl.py              NETWORK RULE / SECRET / EXTERNAL ACCESS INTEGRATION builder + grammar check
snowflake/snowpark_ingest.py  Snowpark DB-API (recommended) and JDBC (fallback) recipe renderers
tests/                        57 offline unit tests covering all of the above
run_tests.py                  entry point: python run_tests.py
```

Every doc claim below is tagged `[verified via WebSearch, doc URL cited]` or
`[primary source: <URL>, fetched directly]`. **All Databricks-doc, Snowflake-doc, and
`docs.intersystems.com` claims in this file are the first kind** — this session's
network egress policy blocks direct `curl`/`WebFetch` to `docs.databricks.com`,
`docs.snowflake.com`, `learn.microsoft.com`, and `docs.intersystems.com` (confirmed:
`CONNECT tunnel failed, response 403` / `EGRESS_BLOCKED` on every one of them). GitHub
and PyPI were reachable directly, so the `iris-pgwire` claims are the second kind. See
`STATUS.md` for the full breakdown.

---

## Path A: Databricks — Unity Catalog JDBC connection ("bring your own driver")

### The mechanism

Lakehouse Federation bundles native connectors for MySQL, PostgreSQL, Redshift,
Snowflake, SQL Server, Azure Synapse, BigQuery, and Teradata. For anything else —
including IRIS — Databricks documents a **JDBC Unity Catalog connection**: you upload
your own driver JAR to a Unity Catalog volume, create a `CONNECTION` object of
`TYPE JDBC`, and layer a `FOREIGN CATALOG` on top so the source appears as
`catalog.schema.table` to any cluster or SQL warehouse.
[verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/connect/jdbc-connection>,
<https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-connection>]

### The DDL (`databricks/ddl.py`)

```sql
CREATE CONNECTION IF NOT EXISTS iris_federation TYPE JDBC
ENVIRONMENT (
  java_dependencies '["/Volumes/main/drivers/jars/intersystems-jdbc-3.8.jar"]'
)
OPTIONS (
  url 'jdbc:IRIS://iris.example-hospital.internal:1972/HSFHIR',
  user 'spark_reader',
  password '<password-or-secret-ref>',
  externalOptionsAllowList 'dbtable,query,partitionColumn,lowerBound,upperBound,numPartitions'
);

CREATE FOREIGN CATALOG IF NOT EXISTS iris_federation_catalog
USING CONNECTION iris_federation
OPTIONS (database 'HSFHIR');
```

This is exactly the shape `databricks/ddl.py` renders (see
`build_create_connection_ddl` / `build_create_foreign_catalog_ddl`), and it is checked
against an offline grammar validator (`validate_create_connection_grammar`,
`validate_create_foreign_catalog_grammar`) so a future edit to the builder that drops
a required clause or unbalances a quote fails a unit test rather than failing at
`CREATE` time on a real workspace.

Facts baked into the builder, each independently confirmed by more than one search
result against the cited URLs:

- `java_dependencies` accepts **only** a Unity Catalog volume path
  (`/Volumes/<catalog>/<schema>/<volume>/...`) — the builder rejects anything else.
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/connect/jdbc-connection>]
- The **documented default** `externalOptionsAllowList` is exactly
  `dbtable,query,partitionColumn,lowerBound,upperBound,numPartitions` — this is the
  module's own default (`DEFAULT_EXTERNAL_OPTIONS_ALLOW_LIST`).
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/connect/jdbc-connection>]
- `host`, `port`, `serverName`, `portNumber`, `instanceName`, and `url` **can never**
  be placed in the allow list or set at query time, regardless of what the allow list
  says — the builder raises `InvalidDdl` if a caller tries.
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/connect/jdbc-connection>]
- `CREATE FOREIGN CATALOG` requires either connection ownership or the
  `CREATE FOREIGN CATALOG` privilege, and Databricks Runtime 13.1+.
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-connection>]

IRIS connectivity facts the URL builder relies on (`com.intersystems.jdbc.IRISDriver`,
`jdbc:IRIS://host:port/NAMESPACE`) match the reference table already in
[`../README.md`](../README.md). Direct verification against `docs.intersystems.com`
was blocked in this session (see `STATUS.md`); these facts are otherwise consistent
across every community IRIS project checked (`iris-pgwire`, `sqlalchemy-iris`).

### The read (`databricks/spark_read_options.py`, `databricks/spark_read_iris_notebook.py`)

Two ways to actually pull rows, both built on the same underlying Spark JDBC data
source and therefore both eligible for Spark's own Catalyst-level filter pushdown
(`PushedFilters` in `.explain()`):

1. **Plain `spark.read.format("jdbc")`**, no Unity Catalog object at all — works on
   any cluster with the driver JAR installed as a library. This is the fallback the
   task asked for, and it is what `spark_read_iris_notebook.py` demonstrates.
2. **Through the Unity Catalog connection** (`spark.read.table("iris_federation_catalog.HSFHIR.Patient")`)
   — governed and reusable, but restricted at query time to whatever is in
   `externalOptionsAllowList`.

Partitioning (`shared/partitioning.py`, unit-tested): `partitionColumn` must be
numeric/date/timestamp; `lowerBound`/`upperBound` set partition **stride only** — they
do **not** filter which rows come back (a documented, common misconception) — and
`numPartitions` caps both parallelism and the number of concurrent JDBC connections
opened against IRIS, so it must be sized against what IRIS can sustain, not just
against cluster core count. [verified via WebSearch, doc URL cited:
<https://docs.databricks.com/aws/en/query-federation/performance-recommendations>,
general Spark JDBC data source documentation]

**Important limitation, confirmed by search, that matters for anyone reading this as
"just like the native connectors":** JDBC-based bring-your-own-driver connections do
**not** get the same optimizer-level pushdown as the eight named native connectors.
Specifically:
- `remote_query`, the table-valued function that lets Databricks SQL push an arbitrary
  query (with filters/aggregates/joins) down to the source, is documented as
  supporting only **BigQuery, MySQL, Oracle, PostgreSQL, Redshift, Snowflake, SQL
  Server, Teradata** — IRIS via bring-your-own JDBC is not eligible.
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/query-federation/remote-queries>]
- More generally: "JDBC data sources do not support predicate pushdown and also don't
  expose statistics to the query optimizer" at the Lakehouse Federation SQL-engine
  layer for generic JDBC connections — pushdown for a bring-your-own connection is
  effectively limited to what you put in `dbtable`/`query` yourself, plus whatever
  Spark's own DataFrame-level filter pushdown does on top.
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/query-federation/remote-queries>]

This is the central piece of evidence for the recommendation below.

### Is `iris-pgwire` + the native PostgreSQL connector the better path?

**Short answer: probably yes for Databricks, and it is the more promising of the two
paths, but it is UNVERIFIED — nobody has run it.**

Evidence for:

- PostgreSQL is one of the eight named Lakehouse Federation connectors, which means it
  gets full documented pushdown (filter, limit, aggregate, and — per search results —
  join pushdown) and `remote_query` eligibility that bring-your-own JDBC does not.
  [verified via WebSearch, doc URL cited: <https://docs.databricks.com/aws/en/query-federation/database-federation>]
- `intersystems-community/iris-pgwire`'s own README lists **"Java: PostgreSQL JDBC"**
  as a verified client, and it is the exact same driver family Databricks' native
  PostgreSQL connector uses under the hood.
  [primary source: <https://github.com/intersystems-community/iris-pgwire/blob/main/README.md>, fetched directly]
- pgwire implements SCRAM-SHA-256 and OAuth 2.0 auth, and a `strict_ddl` /
  `INFORMATION_SCHEMA`-backed catalog layer specifically built for ORM/BI-tool
  introspection (Superset, Metabase, Grafana, Tableau are all documented as working
  through the plain PostgreSQL driver path).
  [primary source: <https://github.com/intersystems-community/iris-pgwire/blob/main/docs/BI_TOOLS.md>, fetched directly]

Evidence against / open risk:

- pgwire's own docs are explicit that catalog support is **partial**: it emulates
  exactly 6 `pg_catalog` tables (`pg_class`, `pg_attribute`, `pg_constraint`,
  `pg_index`, `pg_namespace`, `pg_attrdef`) for ORM introspection, translating from
  `INFORMATION_SCHEMA` — it does **not** implement the full `pg_catalog` surface.
  [primary source: <https://github.com/intersystems-community/iris-pgwire/blob/main/docs/PG_CATALOG.md>, fetched directly]
- pgwire's own known-limitations doc rates `pgAdmin`/`Metabase` compatibility as only
  "Partial (some features require pg_catalog)" — Databricks' native PostgreSQL
  federation connector is a different, unknown client against that same partial
  surface, and nobody has tested it.
  [primary source: <https://github.com/intersystems-community/iris-pgwire/blob/main/KNOWN_LIMITATIONS.md>, fetched directly]
- pgwire has no native TLS termination (recommends nginx/HAProxy in front) and a
  5-connection cap on IRIS Community Edition — both solvable, both require Ops work
  before pointing a production Databricks workspace at it.
  [primary source: <https://github.com/intersystems-community/iris-pgwire/blob/main/README.md>, fetched directly]

**Recommendation**: the bring-your-own JDBC connection (Path A above) is the safer,
lower-risk *first* recipe to publish and validate, because it needs nothing from
`iris-pgwire` and its limitations (no `remote_query`, no aggregate pushdown) are fully
documented up front. The `iris-pgwire` + native-Postgres-connector path is the
higher-upside follow-on — worth a real proof-of-concept against a live Databricks
workspace — but it is not something this task can validate offline, and it inherits
every open pgwire catalog-compatibility question. See `STATUS.md` → UNVERIFIED.

---

## Path B: Snowflake — no bring-your-own JDBC federation

Snowflake has no equivalent of Unity Catalog's JDBC connection object: there is no
`CREATE CONNECTION ... TYPE JDBC` for querying an arbitrary external OLTP database
live, and no query-federation layer at all. Four candidates were evaluated against
primary/secondary sources:

| Candidate | Maturity | Verdict |
| --- | --- | --- |
| **Snowpark Python DB-API** (`session.read.dbapi`) + `psycopg2` via `iris-pgwire` | **GA** | **Recommended** |
| Snowpark Python JDBC (`session.read.jdbc`) with IRIS's own JDBC driver | Public preview | Fallback (no pgwire dependency, but preview-only) |
| Openflow custom NiFi processor | GA product, custom processors are DIY/unsupported | Loses: highest effort, no vendor support for the custom part |
| External tables / Iceberg over Parquet | GA (storage-integration/Iceberg features) | Loses: solves the wrong problem (a lake table format, not a live-query bridge); needs a *separate* IRIS→Parquet export pipeline this task cannot build without Docker/IRIS |

### Why Snowpark DB-API + iris-pgwire wins

- Snowpark Python's **DB-API integration is GA**, and Snowflake's own examples name
  `psycopg2`, `oracledb`, and `pymssql` as the kind of DBAPI 2.0-compliant driver it
  expects — `psycopg2`/`psycopg` is exactly such a driver.
  [verified via WebSearch, doc URL cited: <https://docs.snowflake.com/en/developer-guide/snowpark/python/reading-data>]
- `iris-pgwire` turns IRIS into a real PostgreSQL wire-protocol endpoint, so
  `psycopg2.connect(...)` against it is a normal DBAPI 2.0 connection — no JAR upload,
  no preview-feature risk, and it reuses the exact same `iris-pgwire` dependency Path A
  already evaluates for Databricks (one community project, two vendor paths).
  [primary source: <https://github.com/intersystems-community/iris-pgwire>, fetched directly]
- The Snowpark **JDBC** API (the alternative that needs no pgwire at all) is
  documented as **public preview**, not GA, as of this research — a real but
  strictly weaker fallback if pgwire is unavailable or its catalog gaps turn out to
  matter for a given IRIS schema.
  [verified via WebSearch, doc URL cited: <https://docs.snowflake.com/en/developer-guide/snowpark/python/snowpark-jdbc>]

### Why the others lose

- **Openflow custom processor**: Openflow itself (NiFi-based, BYOC or Snowflake-hosted)
  is a real, GA Snowflake product with a real connector catalog, but *building a new
  custom processor* for a source with no existing connector is explicitly framed by
  Snowflake's own guidance as "build it like a product, not a script" — auth quirks,
  pagination, incremental sync, backoff — and any such custom component is
  **unsupported by Snowflake**, with the org left owning maintenance.
  [verified via WebSearch, doc URL cited: <https://docs.snowflake.com/en/user-guide/data-integration/openflow/about>]
  Far higher effort than a Python function for the same outcome (rows land in a
  Snowflake table), so it loses on effort with no compensating capability gain for a
  single-source, batch-ingestion use case.
- **External tables / Iceberg over Parquet**: this is the right tool for querying data
  that already sits in object storage as Parquet/Iceberg — it is not a mechanism for
  reaching a *live* OLTP system. Using it for IRIS would require standing up a
  separate, ongoing IRIS→Parquet export pipeline (something to unload IRIS tables,
  schedule it, land files in S3/Azure/GCS) before Snowflake ever sees a row, which is
  strictly more moving parts than a single Snowpark function for the same batch-load
  outcome, and this task has no IRIS instance to build or test that exporter against.
  [verified via WebSearch, doc URL cited: <https://docs.snowflake.com/en/user-guide/data-unload-s3>,
  <https://docs.snowflake.com/en/user-guide/tables-iceberg>]

### The setup DDL (`snowflake/ddl.py`, `snowflake/snowpark_ingest.py`)

```sql
CREATE OR REPLACE NETWORK RULE iris_pgwire_network_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('iris.example-hospital.internal:5432');

CREATE OR REPLACE SECRET iris_pgwire_secret
  TYPE = PASSWORD
  USERNAME = '_SYSTEM'
  PASSWORD = '<password>';

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION iris_pgwire_access_integration
  ALLOWED_NETWORK_RULES = (iris_pgwire_network_rule)
  ALLOWED_AUTHENTICATION_SECRETS = (iris_pgwire_secret)
  ENABLED = TRUE;
```

This three-object shape (network rule → secret → integration, referenced by name in
that order) is what Snowflake's external-access-integration documentation describes
for letting a Python UDF/stored procedure reach an external host.
[verified via WebSearch, doc URL cited:
<https://docs.snowflake.com/en/sql-reference/sql/create-external-access-integration>,
<https://docs.snowflake.com/en/developer-guide/external-network-access/creating-using-external-network-access>]
`snowflake/ddl.py` renders and offline-grammar-validates all three; `snowpark_ingest.py`
renders the Python function body (`session.read.dbapi(...)`) that uses them, pulling
the password from the Snowflake `SECRET` at call time via
`_snowflake.get_generic_secret_string` — never embedding it in source.

---

## What is and isn't tested

`shared/`, `databricks/ddl.py`, `databricks/spark_read_options.py`, `snowflake/ddl.py`,
and `snowflake/snowpark_ingest.py` are pure Python with zero third-party runtime
dependencies (tests need only `pytest`). 57 tests cover:

- JDBC URL / pgwire DSN construction and rejection of unsafe hosts/ports/identifiers
- SQL-literal escaping (embedded single quotes)
- The Databricks `CREATE CONNECTION`/`CREATE FOREIGN CATALOG` DDL shape, including
  the documented default allow-list and the documented never-allowed options
- An offline grammar validator for both Databricks DDL statements and all three
  Snowflake DDL statements (keyword order, required clauses, balanced quoting) —
  this is as close to "syntax-checked against the documented grammar" as this
  environment allows without a real SQL parser or a live endpoint
- Spark JDBC partition-plan math (stride vs. row count vs. max-partitions cap vs.
  value-span cap) and its `spark.read.format("jdbc")` options mapping
- That the rendered Snowpark/Spark code snippets never embed a real password

`databricks/spark_read_iris_notebook.py` is illustrative and **not** executed by the
test suite — it references `spark`/`dbutils`, which do not exist outside a Databricks
cluster. Run `run_tests.py` for what actually ran:

```
python run_tests.py
```

See [`STATUS.md`](STATUS.md) for the full verified/unverified/human-actions breakdown.

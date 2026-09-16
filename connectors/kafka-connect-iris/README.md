# Kafka Connect connector for InterSystems IRIS

Source and sink connectors for the [Kafka Connect](https://kafka.apache.org/documentation/#connect)
framework, targeting InterSystems IRIS over JDBC.

**Read [STATUS.md](STATUS.md) before trusting any claim here about readiness.**
This is a reference implementation built and tested in an environment with
no running IRIS instance and no Kafka broker. It compiles, and its JUnit
suite passes for real (pasted command output is in STATUS.md), but nothing
in this directory has ever run against a live IRIS server or a live
Kafka Connect worker.

## Why this exists

This connector answers gap #10 in [`../../research/ecosystem-connector-gaps.md`](../../research/ecosystem-connector-gaps.md):
IRIS has no listing on [Confluent Hub](https://www.confluent.io/hub/), the
browsable connector catalog with a verified-partner program (co-marketing
included). Community Kafka adapters for IRIS exist
([`confluent-kafka-iris`](https://openexchange.intersystems.com/package/confluent-kafka-iris)),
and IRIS itself ships built-in Kafka adapters, but the community has
described the built-in adapters as proof-of-concept quality: **no
partition support, no non-auto offset handling, and Java errors that
aren't translated to IRIS-level errors.** This connector exists to answer
those specific three complaints:

| Critique | Where this connector addresses it |
| --- | --- |
| No real partition support | [`TaskPartitioner`](src/main/java/com/intersystems/kafka/connect/iris/source/TaskPartitioner.java) splits a multi-table source across `tasks.max` tasks instead of running as one unsplittable unit. See `IrisSourceConnector.taskConfigs`. |
| No non-auto offset handling | `incrementing.initial` / `timestamp.initial` let an operator pin an explicit starting position on first run, instead of the connector inferring one (e.g. always the current max, silently dropping backlog). See [`IrisSourceConnectorConfig`](src/main/java/com/intersystems/kafka/connect/iris/source/IrisSourceConnectorConfig.java) and [`TableQuerier`](src/main/java/com/intersystems/kafka/connect/iris/source/TableQuerier.java). |
| Java errors not translated to IRIS-level errors | Every JDBC call is wrapped so a `SQLException` (which carries IRIS's own `SQLCODE`/`SQLState`) propagates to the Connect framework as-is or as the cause of a `ConnectException`/`RetriableException`/dead-letter report -- not swallowed or replaced by a generic Java error. See `IrisSourceTask.poll` and `IrisSinkTask.writeChunk`. |

## What's here

```
kafka-connect-iris/
├── pom.xml                          Maven build (see STATUS.md for real build output)
├── src/main/java/.../iris/
│   ├── Version.java                 Wires Connector.version() to the real build version
│   ├── jdbc/                        The JDBC connection seam (production + test doubles plug in here)
│   ├── source/                      IrisSourceConnector, IrisSourceTask, TableQuerier, TaskPartitioner
│   └── sink/                        IrisSinkConnector, IrisSinkTask, IrisTableWriter, DeadLetterHandler
├── src/test/java/...                JUnit 5 + Mockito + H2 (see the H2 caveat below)
├── config/*.properties.example      Example connector configs (documentation only, never run)
├── README.md                        This file
├── PUBLISHING.md                    Confluent Hub submission requirements
└── STATUS.md                        VERIFIED / UNVERIFIED / HUMAN ACTIONS REQUIRED
```

## The H2 caveat (read this before trusting the test suite)

**H2 is a STAND-IN FOR IRIS, NOT IRIS.** This environment has no running
IRIS instance and no Docker daemon (see `../CLAUDE.md` and
`../README.md`), so every JDBC-facing test in this project runs against
[H2](https://www.h2database.com/), an in-memory ANSI-SQL database used
purely because it *speaks JDBC over java.sql.Connection* the same way IRIS
does. H2's actual SQL dialect, locking model, and type system differ from
IRIS's in ways that matter for a connector:

- H2 does **not** implement IRIS's `INSERT OR UPDATE` statement
  (`InsertMode.UPSERT_NATIVE`). That code path has **zero** automated test
  coverage in this repository.
- Timestamp precision, timezone handling, and numeric type coercion can
  differ between H2 and IRIS's JDBC driver.
- H2's transaction/locking semantics (what happens to a transaction after
  one statement in it throws) are not guaranteed identical to IRIS's.

**What passing tests here prove:** the connector's Java logic -- query
construction, offset advancement and resume, task partitioning, batching,
the portable upsert's try-UPDATE-then-INSERT branching, retry/backoff, and
dead-letter routing -- behaves as designed against a real `java.sql`
JDBC round trip. **What passing tests here do NOT prove:** that any of
this works against real IRIS. See [STATUS.md](STATUS.md) for the exact
scope of that gap.

## Building

```bash
cd connectors/kafka-connect-iris
mvn package
```

Real, pasted output from this exact command is in STATUS.md. Summary of
what a clean build does:

- Compiles against `org.apache.kafka:connect-api:3.7.1` (`provided` scope --
  the Connect worker supplies this at runtime).
- Bundles `com.intersystems:intersystems-jdbc:3.10.5` at compile scope --
  the one runtime dependency the Connect worker does *not* already have.
  These Maven Central coordinates were verified reachable during this
  build (see STATUS.md for the exact `curl`/metadata output); they are
  InterSystems' own published driver, distributed via
  [`intersystems-community/iris-driver-distribution`](https://github.com/intersystems-community/iris-driver-distribution).
- Produces `target/kafka-connect-iris-<version>.jar`. This is a plain jar,
  **not** a Confluent Hub component archive -- see PUBLISHING.md for what
  packaging for the Hub actually requires and why that step was not
  attempted here.

## Testing

```bash
mvn test
```

JUnit 5 + Mockito + H2, fully offline (no Docker, no API key, no network),
following the model of `../../careconnect-sdoh/evals`. 57 tests, all
passing as of this writing -- see STATUS.md for the pasted `mvn test`
output this claim is based on.

## Configuring the source connector

See [`config/iris-source.properties.example`](config/iris-source.properties.example)
and [`IrisSourceConnectorConfig`](src/main/java/com/intersystems/kafka/connect/iris/source/IrisSourceConnectorConfig.java)
for the full config surface. Highlights:

- `mode`: `bulk`, `incrementing`, `timestamp`, or `timestamp+incrementing`.
- `table.whitelist` (comma-separated, parallelized across tasks) **or**
  `query` (one custom SELECT, always exactly one task -- see
  `TableQuerier`'s javadoc for why splitting an arbitrary query safely is
  out of scope here).
- `incrementing.initial` / `timestamp.initial`: the non-auto starting
  offset for a table's first-ever run.
- `poll.interval.ms`, `batch.max.rows`, `topic.prefix`, `db.timezone`,
  `timestamp.delay.ms`.

Offsets are resumed the standard Kafka Connect way: on `start()`, each
table's `TableQuerier` is seeded from
`context.offsetStorageReader().offset(...)` for that table's source
partition (`{"table": "<name>"}`), falling back to the configured initial
offset only if nothing has ever been committed for it.

## Configuring the sink connector

See [`config/iris-sink.properties.example`](config/iris-sink.properties.example)
and [`IrisSinkConnectorConfig`](src/main/java/com/intersystems/kafka/connect/iris/sink/IrisSinkConnectorConfig.java).
Highlights:

- `table.name.format`: destination table, with `${topic}` substituted per record.
- `insert.mode`: `insert`, `upsert` (alias for the tested, portable
  strategy), `upsert_portable`, or `upsert_native` (IRIS's own
  `INSERT OR UPDATE` -- untested here, see the H2 caveat above).
- `pk.fields`, `batch.size`, `max.retries`, `retry.backoff.ms`.
- Dead-letter routing goes through the framework's own
  `SinkTaskContext.errantRecordReporter()` (available since Kafka Connect
  2.6 / KIP-610) rather than a hand-rolled DLQ producer -- see
  [`DeadLetterHandler`](src/main/java/com/intersystems/kafka/connect/iris/sink/DeadLetterHandler.java).
  That requires `errors.tolerance` / `errors.deadletterqueue.topic.name`
  to be set on the connector or worker; without it, failures are logged at
  ERROR but not queued.

A row-level failure (e.g. a constraint violation) is dead-lettered without
retrying or failing the rest of its batch. A connection-level failure
(e.g. the database is unreachable) retries the whole batch up to
`max.retries` times before dead-lettering it.

## IRIS connectivity facts this connector relies on

Per `../README.md`'s shared reference table, verified during this task
against public InterSystems documentation (search-snippet access only --
`docs.intersystems.com` itself was not directly fetchable from this
environment's network egress; see STATUS.md):

| Fact | Value |
| --- | --- |
| JDBC driver class | `com.intersystems.jdbc.IRISDriver` (self-registers via JDBC 4 SPI; not `Class.forName`'d explicitly) |
| JDBC URL | `jdbc:IRIS://host:1972/NAMESPACE` |
| Maven Central coordinates (official) | `com.intersystems:intersystems-jdbc` |
| Maven Central coordinates (community build) | `community.intersystems:intersystems-jdbc` |
| Default superserver port | 1972 |
| Default web port | 52773 |
| Default namespace | `USER` |
| Row-limiting SQL clause | Both `TOP n` and `LIMIT n` are supported and documented as equivalent; this connector uses `LIMIT` (also supported by the H2 stand-in, so it's exercised by the test suite) |
| Upsert | `INSERT OR UPDATE table (cols) VALUES (...)` -- IRIS-specific, documented at `RSQL_insertorupdate`, used by `InsertMode.UPSERT_NATIVE` |

## What this is not

- Not a released artifact. Version is `0.1.0-SNAPSHOT` and will stay that
  way until someone builds and runs this against real IRIS and Kafka.
- Not shaded/packaged for Confluent Hub. See PUBLISHING.md.
- Not a drop-in replacement for IRIS's own built-in Kafka adapters in
  production -- it fixes the three specific gaps the community called out,
  but has not been performance-tested, security-reviewed, or run at any
  scale.

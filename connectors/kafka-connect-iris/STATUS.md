# STATUS

Read this before trusting any claim in README.md or PUBLISHING.md.

## VERIFIED

Everything below was actually run in this session; the commands and their
real output are reproduced or summarized with exact figures.

### The build environment has a working Java toolchain

Contrary to this task's initial briefing ("neither Maven nor Gradle is
installed"), both were present and working:

```
$ java -version
openjdk version "21.0.10" 2026-01-20
$ mvn -version
Apache Maven 3.9.11
$ gradle -version
Gradle 8.14.3
```

### Maven Central resolves through the environment's proxy

```
$ curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://repo1.maven.org/maven2/org/apache/kafka/connect-api/3.7.0/connect-api-3.7.0.pom
HTTP 200
```
`search.maven.org` (a different host) was blocked by the proxy
(`curl: (56) CONNECT tunnel failed, response 403`), but `repo1.maven.org` --
the host Maven's default "central" repository actually resolves
artifacts from -- was reachable, so this did not block dependency
resolution.

### InterSystems' IRIS JDBC driver's Maven Central coordinates are real

```
$ curl -sS https://repo1.maven.org/maven2/com/intersystems/intersystems-jdbc/maven-metadata.xml
<metadata>
  <groupId>com.intersystems</groupId>
  <artifactId>intersystems-jdbc</artifactId>
  <versioning>
    ...
    <versions>
      <version>3.0.0</version>
      <version>3.10.1</version>
      <version>3.10.2</version>
      <version>3.10.3</version>
      <version>3.10.4</version>
      <version>3.10.5</version>
      <version>3.11.0</version>
      <version>2018.1.2.609.0</version>
    </versions>
  </versioning>
</metadata>
```
`3.10.5`'s `.jar` and `.pom` both returned `HTTP 200`. A second, separate
community-published groupId also exists and resolves:
`community.intersystems:intersystems-jdbc` (versions 3.8.0/3.8.4/3.8.41).
This project depends on the official `com.intersystems` coordinates.

### The project actually compiles

```
$ mvn compile
...
[INFO] BUILD SUCCESS
```
23 `.class` files produced under `target/classes`.

### Maven resource filtering wires `Version.get()` to the real build version

```
$ cat target/classes/kafka-connect-iris-version.properties
version=0.1.0-SNAPSHOT
```
(matches `pom.xml`'s `<version>`, not a hardcoded placeholder).

### The full JUnit suite passes

```
$ mvn -o package   # offline, all deps already cached from the online run above
...
[INFO] Tests run: 10, Failures: 0, Errors: 0, Skipped: 0 -- TableQuerierH2Test
[INFO] Tests run: 5,  Failures: 0, Errors: 0, Skipped: 0 -- IrisSourceConnectorTest
[INFO] Tests run: 7,  Failures: 0, Errors: 0, Skipped: 0 -- TaskPartitionerTest
[INFO] Tests run: 10, Failures: 0, Errors: 0, Skipped: 0 -- IrisSourceConnectorConfigTest
[INFO] Tests run: 3,  Failures: 0, Errors: 0, Skipped: 0 -- IrisSourceTaskH2Test
[INFO] Tests run: 8,  Failures: 0, Errors: 0, Skipped: 0 -- IrisSinkConnectorConfigTest
[INFO] Tests run: 6,  Failures: 0, Errors: 0, Skipped: 0 -- IrisSinkTaskH2Test
[INFO] Tests run: 7,  Failures: 0, Errors: 0, Skipped: 0 -- IrisTableWriterH2Test
[INFO] Tests run: 1,  Failures: 0, Errors: 0, Skipped: 0 -- VersionTest
[INFO] Tests run: 57, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
```
57/57 tests pass. This was run twice (once online to populate the local
Maven repo, once fully offline with `-o` to rule out any network
dependency at test time) with identical results.

### A real jar is produced

```
$ ls -la target/kafka-connect-iris-0.1.0-SNAPSHOT.jar
-rw-r--r-- 1 root root 49642 ... target/kafka-connect-iris-0.1.0-SNAPSHOT.jar
$ unzip -p target/kafka-connect-iris-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
Manifest-Version: 1.0
Implementation-Title: kafka-connect-iris
Implementation-Version: 0.1.0-SNAPSHOT
```
It contains only this project's own 15 `.class` files (source: 6, sink: 6,
jdbc: 2, root: 1) plus the version properties file -- confirmed via `jar
tf`. It does **not** contain `intersystems-jdbc`'s classes or any other
dependency; see UNVERIFIED for what that means for deployability.

### IRIS SQL facts cited in README.md, as returned by search-result snippets

`docs.intersystems.com` could not be fetched directly in this environment
(`WebFetch` returned `EGRESS_BLOCKED`), so these are from `WebSearch`
result snippets quoting that domain, not a direct read of the page:

- `TOP (SQL)` and `LIMIT (SQL Clause)` reference pages exist and describe
  `LIMIT numRows` as "functionally identical to a TOP clause" -- basis for
  this connector's use of `LIMIT` in generated queries (also compatible
  with the H2 stand-in, so it's exercised by the test suite).
- `INSERT OR UPDATE (SQL)` reference page exists, described as: attempts
  an insert first, and on a unique-key violation, converts to an update of
  the matching row -- basis for `InsertMode.UPSERT_NATIVE`.
- `%NOLOCK`, `%STARTTABLE` and other query hints are documented as valid
  optimization directives, though no MERGE-statement page was found
  (consistent with IRIS not having a standard `MERGE` and using
  `INSERT OR UPDATE` instead).

### The two ConnectionFactory-seam facts

- `com.intersystems.jdbc.IRISDriver` is never `Class.forName`'d in
  `DriverManagerConnectionFactory` -- confirmed by reading that class's own
  source in this repo, not an external claim.
- Every JDBC access point in `IrisSourceTask`/`IrisSinkTask` goes through
  the `ConnectionFactory` interface, confirmed by grep: no other file in
  `src/main` calls `DriverManager` directly except
  `DriverManagerConnectionFactory` itself.

## UNVERIFIED

This is the larger section, by design -- see the task's own framing.
Nothing below has been checked against a real IRIS instance, a real Kafka
broker, or a real Kafka Connect worker, because none of those exist in
this environment.

- **Nothing here has run against real IRIS.** Every test uses H2 (see
  README.md's "H2 caveat" section for specifics on where H2's SQL dialect,
  locking, and type system are known to diverge from IRIS's). This
  includes, specifically:
  - The exact SQL this connector generates (`LIMIT`, parameterized
    timestamp/incrementing WHERE clauses, `INSERT OR UPDATE`) has never
    been run against IRIS's actual SQL parser.
  - `InsertMode.UPSERT_NATIVE` (IRIS's `INSERT OR UPDATE`) has **no**
    automated test coverage at all, against anything, in this repository.
  - Column type mapping between IRIS JDBC types and Java (via
    `ResultSet.getObject`/`getLong`/`getTimestamp`) is assumed, not tested,
    against the real `intersystems-jdbc` driver's behavior.
  - `DriverManagerConnectionFactory`'s claim that the driver self-registers
    via JDBC 4 SPI (so no `Class.forName` is needed) has not been
    confirmed by actually loading `intersystems-jdbc-3.10.5.jar` and
    opening a connection -- only the jar's *existence* on Maven Central
    was verified, not its contents or runtime behavior.
- **Nothing here has run inside an actual Kafka Connect worker.** No
  `connect-standalone.sh`/`connect-distributed.sh` process, no Connect
  REST API call, no real `SourceTaskContext`/`SinkTaskContext` --
  everything framework-side in the tests is a Mockito mock standing in for
  those. In particular:
  - Real offset-commit timing/`preCommit` interaction with a live offset
    topic is untested.
  - The `ErrantRecordReporter` dead-letter path is untested against a real
    DLQ topic/producer -- only that `IrisSinkTask` calls
    `reporter.report(...)` with the right arguments when given a mock.
  - `poll()`'s throttling (`Thread.sleep` based on `poll.interval.ms`) has
    not been observed under real Connect scheduling.
- **No Kafka broker was available**, so no end-to-end record (produced by
  the source connector, consumed by the sink connector, or consumed by any
  real consumer) has ever actually flowed through a topic.
- **No performance/load testing** of any kind (batch sizing, poll
  interval, connection pooling -- there is none -- under real volume).
- **No security review.** Credentials handling is `ConfigDef.Type.PASSWORD`
  (masked in logs/REST responses per Kafka Connect convention) and nothing
  more; no review of e.g. SQL injection surface for the `query` config
  (which is inherently a raw-SQL-execution config, same as every other
  JDBC source connector's equivalent) or table/column name interpolation
  (`table.whitelist` values and `pk.fields`/column names are concatenated
  directly into generated SQL, not parameterized, because they are DDL
  identifiers rather than data values -- but this has not been reviewed by
  anyone but the author of this same code).
- **`docs.intersystems.com` was never directly read in this session.**
  Every IRIS-SQL-syntax and JDBC-coordinate claim attributed to it came
  from `WebSearch` result snippets, which quote fragments of the target
  page chosen by the search backend, not the full page. `WebFetch` against
  that domain returned `EGRESS_BLOCKED` on every attempt.
- **`docs.confluent.io` and `www.confluent.io` were never directly read**
  either (same `EGRESS_BLOCKED` result). Everything in PUBLISHING.md is
  from `WebSearch` snippets of those domains. In particular, the *current*
  state of Confluent's Verified Integration program (one tier vs. two,
  exact current requirements) returned inconsistent signals across
  different search results and needs direct confirmation.
- **No Confluent Hub component archive was built.** `manifest.json`,
  `lib/`/`etc/`/`doc/`/`assets/` packaging, and validation against the real
  `confluent-hub-client` were all out of scope for this session (no
  Confluent tooling available, and doing it without validation would have
  produced an unverified artifact anyway).
- **No InterSystems ⟷ Confluent partnership was found** in public sources
  searched. Whether InterSystems already holds Confluent partner status
  (a likely prerequisite for the Verified tier) is unknown to this session.
- **This connector's relationship to `confluent-kafka-iris`** (the
  existing community package on Open Exchange cited in
  `../../research/ecosystem-connector-gaps.md`) was not investigated --
  whether that package already covers some or all of this connector's
  scope, and whether it should be extended instead of duplicated, is an
  open question this session did not resolve.
- **Java/Kafka version compatibility range.** Built and tested against
  JDK 21 and `connect-api:3.7.1` only. Compatibility with older Connect
  runtimes (down to whatever minimum IRIS's own docs would target) is
  unverified. `SinkTaskContext.errantRecordReporter()`'s `NoSuchMethodError`
  fallback in `DeadLetterHandler`/`IrisSinkTask.safeErrantRecordReporter`
  is defensive code for pre-2.6 Connect runtimes; it has never actually
  been exercised against one.

## HUMAN ACTIONS REQUIRED

1. **Get a real IRIS instance and re-run this entire test suite's SQL
   against it**, not just H2. At minimum: table creation matching this
   project's test fixtures, all four source modes, both upsert strategies
   (`upsert_portable` and especially `upsert_native`, which has zero
   coverage today), and a look at exactly what Java types
   `intersystems-jdbc` hands back for IRIS's timestamp/numeric types via
   `ResultSet.getObject`.
2. **Stand up a real Kafka Connect worker** (standalone is enough to
   start) and load both connectors via the `config/*.properties.example`
   files (renamed, with real `connection.url`/credentials) to confirm they
   actually start, `taskConfigs()` produces something the framework
   accepts, and records flow end-to-end through a real topic.
3. **Directly read `docs.intersystems.com`'s SQL reference pages** (TOP,
   LIMIT, INSERT OR UPDATE, and the JDBC connectivity guide) from a
   network that isn't proxy-blocked, and correct anything in README.md
   that a full page read contradicts -- this session only had
   search-snippet access.
4. **Directly read `docs.confluent.io`'s Component Archive Specification
   and Verified Integration Program pages** for the same reason, before
   treating PUBLISHING.md as an accurate submission checklist.
5. **Decide who at InterSystems owns this** -- Alliance/Partnerships (for
   any Confluent partner-status question), Interoperability/Data Platform
   product management (for long-term connector ownership), and/or
   Developer Relations (existing owner of `confluent-kafka-iris` on Open
   Exchange) all have a plausible claim; PUBLISHING.md section 4 lays out
   the reasoning but a named decision is needed.
6. **Reconcile with `confluent-kafka-iris`** on Open Exchange before
   investing further -- confirm whether this connector duplicates,
   supersedes, or should be merged with that existing community package.
7. **Security review** before any real deployment: this code has had none.
8. **If Confluent Hub packaging is pursued**: either get access to
   Confluent's own Maven repository to use `kafka-connect-maven-plugin`,
   or hand-build the `manifest.json`/`lib/`/`etc/`/`doc/`/`assets/` layout
   per PUBLISHING.md Section 1 and validate it with a real
   `confluent-hub-client install` -- neither was available in this
   session.

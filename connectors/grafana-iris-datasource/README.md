# InterSystems IRIS data source for Grafana

A Grafana backend data source plugin for InterSystems IRIS: a SQL query editor,
a SAM/Prometheus metrics query type, a config editor with the password in
`secureJsonData`, and a health check. Built to close the #1-ranked gap in
[`../../research/ecosystem-connector-gaps.md`](../../research/ecosystem-connector-gaps.md):
IRIS has no listing in the Grafana plugin catalog, while Snowflake and Databricks
both do.

This is staged work per [`../README.md`](../README.md) — built to be extracted into
its own repository, not wired into the rest of `iris-ai-examples`. Read
[`STATUS.md`](./STATUS.md) before trusting any claim about what actually runs.

## Why REST/SQL, not pgwire or a JDBC bridge

Go has no native (cgo-free) IRIS driver. Three access paths were evaluated:

| Path | Pure Go? | Extra deploy step? | Chosen? |
| --- | --- | --- | --- |
| **REST/SQL** — IRIS's `%Api.Atelier` `action/query` endpoint over HTTP on the web port (52773) | Yes — `net/http` + `encoding/json` only | None — ships on every stock IRIS install | **Yes** |
| **pgwire** — PostgreSQL wire protocol via the community `iris-pgwire` gateway + a Go `pgx` driver | Yes | Requires `iris-pgwire` running IRIS-side, which is not part of a stock install | No |
| **JDBC bridge** — shell out to a JVM running `com.intersystems.jdbc.IRISDriver` | No | Requires a JVM at runtime; conflicts with Grafana backend plugins being single static Go binaries | No |

REST/SQL is the only option that works against a stock IRIS instance with nothing
extra to deploy, using only the Go standard library. See the doc comment on
[`pkg/plugin/client/client.go`](./pkg/plugin/client/client.go) for the full
reasoning, and [`pkg/plugin/client/rest_client.go`](./pkg/plugin/client/rest_client.go)
for the implementation.

**The access path is behind an interface** (`client.IRISClient`, in
`pkg/plugin/client/client.go`) specifically so a pgwire- or JDBC-backed client can
be added later without touching the datasource, query-dispatch, or
data-frame-conversion code.

### Endpoints used

| Purpose | Endpoint | Notes |
| --- | --- | --- |
| Run SQL | `POST /api/atelier/v1/{namespace}/action/query` | Body `{"query": "...", "parameters": []}`. Response's `result.content` is an array of JSON objects, one per row, keyed by column name. Requires `Content-Type: application/json` and HTTP Basic auth. |
| SAM/Prometheus metrics | `GET /api/monitor/metrics` | OpenMetrics/Prometheus text exposition format. Built into IRIS since 2020.1, used by SAM. |
| Health check | Reuses the SQL endpoint with `SELECT 1` | Exercises connectivity, auth, and the SQL engine in one call. |

## Attribution

`caretdev/grafana-intersystems-datasource` (Dmitry Maslennikov) already exists as an
unpublished Go/xDBC Grafana plugin for IRIS, streaming SAM metrics with real-time
history, logs, and alerts. It was read via read-only GET for reference only — no code
from it was copied. Two ideas it validated independently arrived at here too: that a
Grafana IRIS plugin should surface SAM metrics as a first-class query type, and that a
Go backend plugin is the right shape for this integration. The REST/SQL transport,
type-inference logic, and every line of Go and TypeScript in this directory are
original to this session.

## Layout

```
main.go                    Backend plugin entrypoint (grafana-plugin-sdk-go)
pkg/plugin/
  client/
    client.go               IRISClient interface + shared types (Column, Row, MetricSample)
    rest_client.go          The only production IRISClient: REST/SQL + SAM metrics over HTTP
  models.go                 jsonData / secureJsonData parsing (PluginSettings)
  frame.go                  QueryResult / []MetricSample -> Grafana data.Frame, with type inference
  datasource.go             QueryData / CheckHealth / Dispose — the Grafana backend contract
src/
  plugin.json               Plugin manifest
  module.ts                 Registers DataSource + ConfigEditor + QueryEditor
  datasource.ts             Frontend DataSource (extends DataSourceWithBackend)
  types.ts                  IRISQuery / IRISDataSourceOptions / IRISSecureJsonData
  components/
    ConfigEditor.tsx         Host, port, namespace, username, password (secureJsonData), TLS, timeout
    QueryEditor.tsx          Query type toggle (SQL / SAM metrics) + SQL text area
provisioning/datasources/    Example Grafana provisioning YAML
PUBLISHING.md                Grafana catalog submission requirements
STATUS.md                   VERIFIED / UNVERIFIED / HUMAN ACTIONS REQUIRED
```

## Building

Backend (Go 1.24.6+):

```bash
go build ./...
go vet ./...
go test ./... -cover
```

Frontend (Node 22):

```bash
npm install
npm run typecheck
npm run build
```

`npm run build` produces `dist/`. It does **not** produce the backend binary — that
needs a matching Go build per target OS/arch (see PUBLISHING.md for the full matrix
Grafana's signing process expects), e.g.:

```bash
GOOS=linux GOARCH=amd64 go build -o dist/gpx_iris_datasource_linux_amd64 .
```

## Configuration

The config editor writes two kinds of data to Grafana:

- **`jsonData`** (plain, visible in the datasource's settings JSON): `host`, `webPort`
  (default 52773), `namespace` (default `USER`), `username`, `useHTTPS`,
  `skipTLSVerify`, `timeoutSeconds` (default 30).
- **`secureJsonData`** (encrypted at rest, never re-sent to the browser): `password`.

`pkg/plugin/models.go`'s `LoadPluginSettings` only ever reads the password from
`DecryptedSecureJSONData["password"]` — never from the plain `jsonData` blob, even if
a `password` key were somehow present there. `pkg/plugin/models_test.go` has a
regression test (`TestLoadPluginSettings_NeverReadsPasswordFromPlainJSONData`) pinning
that down.

## Query types

| `queryType` | What it does |
| --- | --- |
| `sql` (default, including when omitted — keeps older saved queries working) | Runs `queryText` as a single SQL statement via the REST/SQL endpoint and returns one row-per-record frame. |
| `sam_metrics` | Scrapes `/api/monitor/metrics` and returns a wide table: `time` (scrape time), `metric`, one column per distinct label key across all samples, `value`. |

**SAM metrics limitation, stated plainly:** each query is a live snapshot. This
transport has no access to IRIS's own metric history, so a single query cannot
backfill a Grafana time range — Table/Stat panels with a short refresh interval are
the right fit today, not a long-range time-series graph. Real history would need
either IRIS-side retention (e.g. actual Prometheus scraping IRIS and Grafana querying
Prometheus instead) or a caching layer in front of this plugin. Out of scope here.

## Type inference

The REST/SQL transport's plain (non-positional) query call does not return per-column
SQL type metadata — see the doc comment in `rest_client.go`. `pkg/plugin/frame.go`
infers each Grafana field's type from the values actually present in a column: bool,
then numeric, then a handful of IRIS's common timestamp string layouts, falling back
to string when a column is empty or its values don't agree on one type. Every column
is built as a nullable field so a NULL in any row doesn't force the whole column to
string. See `pkg/plugin/frame_test.go` for the cases this covers, including a
regression test that pins column order to the SQL SELECT list order rather than
whatever order Go's JSON decoder or map iteration would produce.

## Testing

There is no running IRIS instance and no Docker daemon in the environment this was
built in (see STATUS.md), so every test is offline: real Go `net/http/httptest`
servers standing in for IRIS's REST endpoints, and hand-written fakes for
`client.IRISClient` in the datasource-layer tests. No test hits the network. Model:
`careconnect-sdoh/evals` (this repo's offline, no-Docker, no-API-key test suite).

```bash
go test ./... -v -cover
```

## Development against a real Grafana + IRIS (not verified in this session)

`docker-compose.yaml` and `provisioning/datasources/datasources.yml` are provided for
a human with Docker to bring up a local Grafana pointed at this plugin and a real IRIS
instance. Neither was run here — see STATUS.md.

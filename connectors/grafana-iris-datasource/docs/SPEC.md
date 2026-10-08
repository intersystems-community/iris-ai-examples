# InterSystems IRIS data source: Phase A spec

Goal: a data source plugin good enough to submit to the Grafana catalog, proved against a real IRIS and
a real Grafana before anything is submitted. Phase B (the submission itself) waits on the publisher
decision (Grafana Cloud org slug, signing class); Phase A does not.

Decisions (2026-10-08): develop here, extract to its own repo before submitting; v1 is SQL plus SAM
metrics; minimum Grafana 11.1.0 with `@grafana/*` pinned to 11.x; test on 11.1 and the latest.

## Requirements

- **PA-01** A SQL error from IRIS MUST reach the user as IRIS's own message. (Found against a real IRIS:
  `status.errors` is an array of objects, not strings.)
- **PA-02** The client MUST be tested against a real IRIS in CI and locally, not only against fakes.
  Shapes asserted: success rows, error object, NULL handling, large result, metrics text.
- **PA-03** The Go SDK MUST be within 2 months of the latest release and not `replace`d (the validator
  makes more than 5 months an Error). `grafanaDependency` MUST be `>=11.1.0` and `@grafana/*` pinned to 11.x.
- **PA-04** SQL queries MUST support the macros `$__timeFilter(col)`, `$__timeFrom()`, `$__timeTo()`,
  Grafana dashboard variables, and a Table or Time series format, so a query can be used in a dashboard.
- **PA-05** The plugin MUST work for alerting (`"alerting": true`): backend-only query path.
- **PA-06** The backend MUST follow the validator's code rules: no `os.Getenv`, file access, `syscall` or
  `fmt.Print`; every returned error carries a `backend.ErrorSource`; response size and row limits.
- **PA-07** The plugin MUST be loaded into a real Grafana 11.1.0 and the latest Grafana, configured through
  the UI, and a query run through a panel. Screenshots come from that run.
- **PA-08** The repo MUST carry what the catalog asks for: `Magefile.go`, CI (build, test, e2e, validate),
  CHANGELOG, README without developer jargon, screenshots declared in `plugin.json`, LICENSE.
- **PA-09** `plugin-validator` MUST report no Errors on the built plugin.

- **PA-10** The data source MUST be read-only by default: a statement that is not a `SELECT` (or `WITH ... SELECT`),
  or that chains a second statement, is refused before it reaches IRIS, unless the data source's "Allow data
  changes" setting is on. Measured on a real IRIS: `/api/atelier` does not apply table-level SQL privileges, so an
  account holding only SELECT on one table could still DELETE its rows through it. Anyone who can edit a panel can
  type any SQL, so IRIS permissions cannot be what protects the data.

## Known facts that shape the work (measured on IRIS 2026.x)

- `POST /api/atelier/v1/{ns}/action/query` returns `result.content` as row objects in SELECT order.
- A NULL arrives as `""` in a string column and `0` in a numeric column, so null and empty are
  indistinguishable on this path. Documented, not fixable without a different transport.
- Typed parameters arrive as strings. 5000-row results come back whole.
- `GET /api/monitor/metrics` is Prometheus text, parsed without error (742 samples). It needs no login by default
  (its web application has authentication level 64).
- `/api/atelier` needs the `%Development` resource, and then runs SQL without enforcing table privileges (see PA-10).
- A DDL `TIMESTAMP` column is a PosixTime: returned as unix microseconds + 2^60, and compared correctly only against
  `CAST('...' AS TIMESTAMP)`, never a bare string literal.

## Out of scope for v1

Logs, application errors, live streaming, the native protocol, OAuth/bearer auth.

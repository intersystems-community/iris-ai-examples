# Changelog

## 0.1.0 (unreleased)

First release.

- SQL queries with the `$__timeFilter(col)`, `$__timeFrom()`/`$__timeTo()` (and column forms) and
  `$__timeGroup(col, step)` macros, dashboard variables, a row limit, and Table or Time series format.
- Epoch-millisecond macros (`$__unixEpochMsFilter`, `$__unixEpochMsFrom`/`To`, `$__unixEpochMsGroup`), and a
  numeric column named `time` or `timeEnd` read as an epoch.
- Annotation queries: any SQL query returning `time`, `timeEnd`, `text` and `tags` can be a dashboard annotation
  source.
- A Web terminal connection over the web port (IRIS 2023.2 or later), which runs queries under the account's
  SQL privileges, through IRIS's `/api/atelier/v7/%SYS/terminal` WebSocket. With a Grafana org per Tenant it keeps
  each Tenant to its own rows on a shared IRIS; `e2e/tenant-isolation.sh` checks that on Grafana 11.1.0 and 13.2.3.
- A showcase dashboard over a synthetic dataset (`e2e/seed-showcase.sh`): two Tenants' deploys, findings, Episodes
  and log-storm rollups in epoch milliseconds, with deploy and Episode annotations.
- A Time series query that returns no rows is an empty panel, not an error.
- SAM metrics query.
- Alerting support.
- Read-only by default; an "Allow data changes" setting lifts the guard.
- Reads PosixTime timestamps, and treats the empty string IRIS sends for NULL as null in a time column.
- Shows IRIS's own SQL error messages, and reports errors with the right status and source.
- Tested against a real IRIS (2026.1) and Grafana 11.1.0 and 13.2.3.

Time bucketing and the row limit follow the feature set of
[grongierisc/grafana-datasource-iris](https://github.com/grongierisc/grafana-datasource-iris) (MIT), reimplemented
here on this plugin's REST client and data-frame code. A SuperServer connection over the community
`go-irisnative` driver was built too and set aside before release, for the web terminal; it is kept on the
`feat/grafana-iris-datasource-native` branch.

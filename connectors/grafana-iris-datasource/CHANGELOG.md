# Changelog

## 0.1.0 (unreleased)

First release.

- SQL queries with the `$__timeFilter(col)`, `$__timeFrom()` and `$__timeTo()` macros, dashboard variables, and
  Table or Time series format.
- SAM metrics query.
- Alerting support.
- Read-only by default; an "Allow data changes" setting lifts the guard.
- Reads PosixTime timestamps, and treats the empty string IRIS sends for NULL as null in a time column.
- Shows IRIS's own SQL error messages, and reports errors with the right status and source.
- Tested against a real IRIS (2026.1) and Grafana 11.1.0 and 13.2.3.

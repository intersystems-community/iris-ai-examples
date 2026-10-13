# Changelog

## 0.1.0 (unreleased)

First release.

- SQL queries with the `$__timeFilter(col)`, `$__timeFrom()`/`$__timeTo()` (and column forms) and
  `$__timeGroup(col, step)` macros, dashboard variables, a row limit, and Table or Time series format.
- A Native connection over the IRIS SuperServer port, which runs queries under the account's SQL privileges.
- SAM metrics query.
- Alerting support.
- Read-only by default; an "Allow data changes" setting lifts the guard.
- Reads PosixTime timestamps, and treats the empty string IRIS sends for NULL as null in a time column.
- Shows IRIS's own SQL error messages, and reports errors with the right status and source.
- Tested against a real IRIS (2026.1) and Grafana 11.1.0 and 13.2.3.

Time bucketing, the row limit and the Native connection follow the feature set of
[grongierisc/grafana-datasource-iris](https://github.com/grongierisc/grafana-datasource-iris) (MIT), reimplemented
here on this plugin's REST client and data-frame code.

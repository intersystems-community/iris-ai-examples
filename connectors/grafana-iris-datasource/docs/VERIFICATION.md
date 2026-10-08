# Verification record

What has been run, against what, and what it found. Written 2026-10-08; update it when it changes.

## Environment

- IRIS: `containers.intersystems.com/intersystems/iris-community:2026.1` (public image, no licence key), run by
  `docker-compose.e2e.yaml`.
- Grafana: 11.1.0 (commit 5b85c4c2) and 13.2.3 (commit 90ffed05), run by `docker-compose.grafana.yaml`.
- One plugin build, made against `@grafana/*` 11.1.13, was loaded into both Grafanas.
- Go SDK v0.297.0 (released 2026-10-07), Go 1.26.5, Node 22.

## Passing

- Go unit tests, TypeScript tests (24), lint and typecheck.
- Real-IRIS Go suite (`go test -tags e2e`): connection, column order, SQL error text, NULL behaviour, 5,000-row
  result, bad password, missing namespace, metrics parsing, time macros on both kinds of timestamp column,
  PosixTime decoding, time series format, the read-only guard (refused by default; lifted by the setting).
- Plugin loaded into Grafana 11.1.0 and 13.2.3: registered, data source provisioned, `Save & test` returns
  "IRIS connection OK", the four-panel demo dashboard renders from live IRIS data, the `$host` variable works,
  errors reach the panel with IRIS's own message and `errorSource: downstream`.
- `@grafana/plugin-validator` on the packaged zip: no Errors except the `braces` advisory below.

## Defects this found that no fake could have

1. Every SQL error was shown as "cannot unmarshal object": IRIS sends `status.errors` as objects, the client
   expected strings.
2. A `TIMESTAMP` column made by DDL came back as an internal number (unix microseconds + 2^60).
3. Comparing that column with a bare string literal silently matched **nothing**; `CAST('...' AS TIMESTAMP)` is right
   for both column kinds. The first version of `$__timeFilter` returned 0 rows.
4. `/api/atelier` does not apply table privileges: an account with `SELECT` on one table could `DELETE` its rows,
   query `%SYS` and read the class dictionary. The plugin is therefore read-only by default.
5. The "Skip TLS verify" setting was accepted and ignored.
6. A numeric NULL arrives as `0` and a string NULL as `""`.
7. The settings page had overlapping labels; the dashboard variable panel ran a stale cached `module.js` (see
   DEVELOPMENT.md).

## Not done

- **Not signed.** Signing needs the Grafana Cloud organisation (Phase B).
- **`osv-scanner` fails on `braces`** (GHSA-vfj7-8cjw-p6xm, published 2026-09-18, vulnerable <= 3.0.3, **no patched
  version exists**). It is a dev-only dependency of jest and eslint, never shipped, and affects every plugin that
  uses them. It also makes the validator skip its code-diff stage. To see those stages locally, downgrade that rule
  in a validator config file.
- **`https://www.intersystems.com` returns 403 to the validator** (bot blocking), a warning only.
- Nothing has been run against a deployed Grafana (the EKS one has no IRIS plugin).
- The minimum IRIS privileges are known (`%Development:U`, database read, `SELECT`), but they do not limit what the
  REST API can do (defect 4).
- Log, application-error and streaming queries, the native protocol and bearer-token auth are out of scope for 0.1.0.

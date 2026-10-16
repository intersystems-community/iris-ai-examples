# IRIS Ecosystem Connectors — staged work

Connectors for catalogs where Snowflake and Databricks are first-class data
sources and InterSystems IRIS is absent. This directory holds the Grafana data
source plugin. The wider gap analysis and the other connector implementations
are kept in a private InterSystems repository.

## Placement caveat — read first

This directory is **staged work, not a decision about where it belongs.** Per
`../CLAUDE.md`, `iris-ai-examples` exists for canonical IRIS **AI demo** examples;
production connectors are a different kind of artifact with different release
cadences, CI needs, and (in most cases) a required home of their own —
here, a Grafana plugin repo.

Everything here is built to be **extracted into its own repository** without
rework. Each subdirectory is self-contained: its own manifest, dependencies,
tests, and README. Nothing here is imported by the three examples in this repo,
and nothing in those examples imports from here.

Deciding the final home is the maintainers' call.

## Verification ceiling in this environment

Two hard limits applied when this was built, and they bound what its STATUS.md
is allowed to claim:

1. **No running IRIS and no Docker daemon.** Nothing here has been
   integration-tested against a live IRIS instance. Tests use fakes and mocks
   and run fully offline, following the model of `../careconnect-sdoh/evals`
   (no Docker, no API key).
2. **No third-party accounts, no submissions.** Publishing a Grafana plugin
   requires credentials and human authorization that did not exist in that
   session. No registry was contacted.

`STATUS.md` separates what is **verified with real command output** from what is
**unverified**, plus the specific human actions needed to finish. Read that file
before trusting anything here.

## Contents

| Directory | Gap addressed |
| --- | --- |
| `grafana-iris-datasource/` | Grafana plugin catalog |

## IRIS connectivity reference

| Surface | Value |
| --- | --- |
| Default superserver port | 1972 |
| Default web port | 52773 |
| REST/SQL endpoint used by the plugin | `%Api.Atelier` `action/query` on the web port |
| PostgreSQL wire protocol | `intersystems-community/iris-pgwire` (community) |

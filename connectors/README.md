# IRIS Ecosystem Connectors — staged work

Implementations of the integration gaps identified in
[`../research/ecosystem-connector-gaps.md`](../research/ecosystem-connector-gaps.md):
catalogs where Snowflake and Databricks are first-class data sources and
InterSystems IRIS is absent.

## Placement caveat — read first

This directory is **staged work, not a decision about where it belongs.** Per
`../CLAUDE.md`, `iris-ai-examples` exists for canonical IRIS **AI demo** examples;
production connectors are a different kind of artifact with different release
cadences, CI needs, and (in most cases) a required home of their own —
a Grafana plugin repo, a Fivetran connector repo, an Airbyte connector directory.

Everything here is built to be **extracted into its own repository** without
rework. Each subdirectory is self-contained: its own manifest, dependencies,
tests, and README. Nothing here is imported by the three examples in this repo,
and nothing in those examples imports from here.

Deciding the final home is the maintainers' call.

## Verification ceiling in this environment

Two hard limits applied to every subdirectory below, and they bound what any
STATUS.md in here is allowed to claim:

1. **No running IRIS and no Docker daemon.** Nothing here has been
   integration-tested against a live IRIS instance. Tests use fakes and mocks
   and run fully offline, following the model of `../careconnect-sdoh/evals`
   (no Docker, no API key).
2. **No third-party accounts, no submissions.** Publishing a Grafana plugin,
   certifying a Fivetran connector, listing on Confluent Hub, or joining the
   Salesforce Zero Copy Partner Network all require credentials and human
   authorization that do not exist in this session. No registry was contacted.

Each subdirectory carries a `STATUS.md` separating what is **verified with real
command output** from what is **unverified**, plus the specific human actions
needed to finish. Read that file before trusting anything here.

## Contents

| Directory | Gap addressed | Rank in analysis |
| --- | --- | --- |
| `grafana-iris-datasource/` | Grafana plugin catalog | 1 |
| `mcp-iris/` | AI agent connector directories | 2 |
| `databricks-snowflake-federation/` | Competitors' own federated source lists | 3 |
| `fivetran-iris/` | Fivetran connector catalog | 4 |
| `fabric-open-mirroring-iris/` | Microsoft Fabric mirroring | 5 |
| `salesforce-zero-copy-iris/` | Salesforce Data Cloud Zero Copy | 6 |
| `tableau-iris/` | Tableau Exchange | 7 |
| `adf-iris/` | Azure Data Factory / Synapse | 8 |
| `airbyte-source-iris/` | Airbyte connector catalog | 9 |
| `kafka-connect-iris/` | Confluent Hub | 10 |

## IRIS connectivity reference

Shared facts each connector depends on:

| Surface | Value |
| --- | --- |
| Python DB-API | `intersystems-irispython` (import `iris`) |
| SQLAlchemy | `sqlalchemy-iris`, URL `iris://user:pass@host:1972/NAMESPACE` |
| JDBC driver class | `com.intersystems.jdbc.IRISDriver` |
| JDBC URL | `jdbc:IRIS://host:1972/NAMESPACE` |
| Default superserver port | 1972 |
| Default web port | 52773 |
| PostgreSQL wire protocol | `intersystems-community/iris-pgwire` (community) |

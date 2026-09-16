# InterSystems IRIS

This page follows the shape of an Airbyte "Documentation" page
(`docs/integrations/sources/<name>.md` in the airbytehq/airbyte monorepo — see
[`docs/integrations/sources/pokeapi.md`](https://github.com/airbytehq/airbyte/blob/master/docs/integrations/sources/pokeapi.md)
for a real example of that convention fetched while building this connector). It lives
at `docs/iris.md` here since this repo is staged outside the monorepo; on contribution
it would move to `docs/integrations/sources/iris.md` and `documentationUrl` in
`metadata.yaml`/`spec.yaml` would resolve to it at
`https://docs.airbyte.com/integrations/sources/iris`.

## Overview

The InterSystems IRIS source connector syncs tables from an
[InterSystems IRIS](https://www.intersystems.com/products/intersystems-iris/) database
via its SQL/DB-API surface. It supports full refresh and incremental (cursor-based)
sync, with catalog discovery driven entirely by `INFORMATION_SCHEMA`.

## Prerequisites

- Network access to the IRIS instance's superserver port (default `1972`).
- An IRIS username/password with `%SQL` `SELECT` privilege on the namespace/schema(s)
  to sync, and privilege to query `INFORMATION_SCHEMA.TABLES`/`.COLUMNS`.

## Setup guide

| Field | Description |
| --- | --- |
| `host` | Hostname or IP of the IRIS instance. |
| `port` | Superserver port. Default `1972`. |
| `namespace` | IRIS namespace to connect to. Default `USER`. |
| `username` / `password` | IRIS credentials. `password` is an `airbyte_secret`. |
| `schemas` | Optional list of SQL schemas to restrict discovery to. |
| `tables` | Optional list of table (or `Schema.Table`) names to restrict discovery to. |
| `connection_timeout_seconds` | DB-API connection timeout. Default `20`. |

See `source_iris/spec.yaml` for the authoritative JSON Schema.

## Supported sync modes

| Sync mode | Supported? | Notes |
| --- | --- | --- |
| Full Refresh - Overwrite | Yes | |
| Full Refresh - Append | Yes | |
| Incremental - Append | Yes, per-table | Only for tables whose primary key is a single non-LOB column — see README.md "Incremental sync". |
| Incremental - Append + Deduped | Not implemented | Would require the same primary-key/cursor plumbing as Append; not built in v1. |

## Type mapping

See [`../README.md#type-mapping`](../README.md#type-mapping) for the full table and
the `%PosixTime`/streams-LOBs/precision caveats — those caveats are load-bearing and
are not repeated here to avoid the two copies drifting.

## Changelog

| Version | Date | Pull Request | Subject |
| --- | --- | --- | --- |
| 0.1.0 | 2026-09-16 | (none yet — not contributed upstream; see `../PUBLISHING.md`) | Initial version: full refresh + PK-based incremental, INFORMATION_SCHEMA discovery. |

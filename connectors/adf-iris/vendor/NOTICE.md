# Third-party content — provenance and licence

The two JSON files in this directory are **unmodified copies of Microsoft's
published Azure Resource Manager schemas**, vendored so that the test suite can
validate generated ARM payloads against the real schema offline. They are not
InterSystems work and are not covered by this repository's licence.

| File | Source |
| --- | --- |
| `Microsoft.DataFactory.2018-06-01.json` | [`Azure/azure-resource-manager-schemas`](https://github.com/Azure/azure-resource-manager-schemas) — `schemas/2018-06-01/Microsoft.DataFactory.json` |
| `arm-common-definitions.json` | [`Azure/azure-resource-manager-schemas`](https://github.com/Azure/azure-resource-manager-schemas) — common definitions |

**Licence:** MIT, per the `LICENSE` file at the root of
`Azure/azure-resource-manager-schemas`. Copyright (c) Microsoft Corporation.

## Why these are vendored rather than fetched

This connector's tests validate generated ARM JSON against Microsoft's actual
schema instead of a hand-written approximation — that validation caught two real
bugs during development (incorrect `integrationRuntimes` casing, and a resource
name that violated ARM's name pattern). Fetching the schema at test time would
make the suite depend on network access, which conflicts with the repo's
offline-test policy in `CLAUDE.md`.

`../schemas/adf-schema-subset.json` is a trimmed subset derived from these files
by `../schemas/build_schema_subset.py`; the subset preserves the relevant
definitions verbatim. Re-run that script to regenerate it after refreshing these
vendored copies.

## Refreshing

These are a point-in-time copy taken 2026-09-16 of the `2018-06-01` API version.
Microsoft revises these schemas, so re-fetch from the upstream repository and
re-run the subset builder before relying on the validation for a newer API
version.

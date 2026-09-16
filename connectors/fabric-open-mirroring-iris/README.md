# fabric-open-mirroring-iris

Publishes InterSystems IRIS tables into a Microsoft Fabric **Open Mirroring**
landing zone: an initial full snapshot, then incremental insert/update/delete
batches, written as Parquet files in the exact folder layout, file naming,
and metadata format Fabric's mirroring engine expects.

Gap this addresses: see
[`../research/ecosystem-connector-gaps.md`](../research/ecosystem-connector-gaps.md)
rank #5 — Fabric mirroring lists Azure SQL, SQL MI, Cosmos DB, Azure
Databricks, PostgreSQL, Snowflake, SQL Server, Oracle, SAP, Google BigQuery,
and more as native mirrored sources. IRIS is absent from that list (confirmed
directly against Microsoft's own source table — see "Current native source
list" below). Open Mirroring is the one Fabric feature that lets a
non-Microsoft, non-partnered party close that gap **today**, without a
Microsoft joint-engineering motion.

Read [`PUBLISHING.md`](PUBLISHING.md) for the two paths to an IRIS tile in
Fabric (Open Mirroring vs. native mirrored source) and how they compare, and
[`STATUS.md`](STATUS.md) for exactly what in this directory is backed by
real, pasted command output versus what still needs a live Fabric tenant to
confirm.

## Is Open Mirroring real, current, and partner-buildable? (verified first, per task instructions)

Yes. Confirmed by fetching Microsoft's own docs (see "Spec citations" below,
all fetched read-only in this session — no OneLake/Azure endpoint was ever
contacted):

> "Open mirroring enables any application to write change data directly into
> a mirrored database in Fabric. Open mirroring is designed to be
> extensible, customizable, and open, and is a powerful feature that extends
> mirroring in Fabric based on [the] open Delta Lake table format."
> — [`open-mirroring.md`](https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring)

Mechanically: you create a mirrored database (Fabric portal, or the "Create
mirrored database" REST API) and get back a **landing zone URL in OneLake**.
Any process that can write files to that URL — with no Microsoft code
review, no partner agreement, no listing anywhere — can push change data in,
and Fabric's mirroring engine turns it into Delta Parquet automatically. That
is the exact "no Microsoft-side connector build required" path the task
asked to confirm, and it is what this connector implements.

## Current native mirroring source list (for comparison)

Fetched directly from Microsoft's docs source table on 2026-09-16:

| Source | Status |
| --- | --- |
| Azure SQL Database | GA |
| Azure SQL Managed Instance | GA |
| Azure Cosmos DB | GA |
| Azure Databricks | GA |
| Azure Database for PostgreSQL | GA |
| Azure Database for MySQL | Preview |
| Snowflake | GA |
| SQL Server | GA |
| Oracle | GA |
| SAP | GA |
| Google BigQuery | GA |
| Dremio catalog | Preview |
| SharePoint List | Preview |
| Open mirrored databases | GA |
| Fabric SQL database | GA |

Source:
[`includes/mirrored-sources-table.md`](https://github.com/MicrosoftDocs/fabric-docs/blob/main/docs/mirroring/includes/mirrored-sources-table.md),
transcluded into
[`overview.md`](https://learn.microsoft.com/en-us/fabric/mirroring/overview).
**InterSystems IRIS is not on this list.** Note for anyone reusing the
original gap-ranking research: Oracle has since moved from "preview" to GA
as of this fetch — the gap itself (IRIS absent) is unchanged, but cite the
live table, not a snapshot, when this matters for a pitch deck.

## Spec citations

Every landing-zone format claim this connector's code and tests depend on
traces to one of these Microsoft Learn pages. Network egress in this sandbox
only reaches `raw.githubusercontent.com`, not `learn.microsoft.com` directly
(see `STATUS.md`); `MicrosoftDocs/fabric-docs` is the actual source
repository Microsoft Learn's Fabric mirroring pages are published from, so
the Markdown fetched from it **is** the Learn page's content, not a
paraphrase — the `learn.microsoft.com` URLs below are the canonical,
human-facing addresses for the same files.

| Claim | Learn URL | Also fetched via |
| --- | --- | --- |
| Landing zone path `Files/LandingZone/<table>/`, `_metadata.json` + `keyColumns`, 20-digit sequential `NNNNNNNNNNNNNNNNNNNN.parquet` filenames, `__rowMarker__` last column with codes 0/1/2/4, `_partnerEvents.json`, column add/drop/rename/type-change rules, cleanup into `_ProcessedFiles` | [fabric/mirroring/open-mirroring-landing-zone-format](https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring-landing-zone-format) | [raw MicrosoftDocs/fabric-docs](https://github.com/MicrosoftDocs/fabric-docs/blob/main/docs/mirroring/open-mirroring-landing-zone-format.md) |
| What Open Mirroring is, Delta Lake basis, no-connector-build model | [fabric/mirroring/open-mirroring](https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring) | [raw MicrosoftDocs/fabric-docs](https://github.com/MicrosoftDocs/fabric-docs/blob/main/docs/mirroring/open-mirroring.md) |
| Native mirrored source list, "Fabric compute used to replicate your data into Fabric OneLake is free" billing note | [fabric/mirroring/overview](https://learn.microsoft.com/en-us/fabric/mirroring/overview) | [raw MicrosoftDocs/fabric-docs](https://github.com/MicrosoftDocs/fabric-docs/blob/main/docs/mirroring/overview.md) |
| Writing to the OneLake landing zone with the Blob/ADLS APIs, `onelake.blob.fabric.microsoft.com` endpoint, temp-file-then-atomic-rename pattern | [fabric/onelake/onelake-apis-in-action](https://learn.microsoft.com/en-us/fabric/onelake/onelake-apis-in-action) | [raw MicrosoftDocs/fabric-docs](https://github.com/MicrosoftDocs/fabric-docs/blob/main/docs/onelake/onelake-apis-in-action.md) |

Pages referenced but **not** fetched in full in this session (found via
search only — do not treat as verified, see `STATUS.md`):
[open-mirroring-tutorial](https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring-tutorial),
the "Create mirrored database" REST API reference.

Community context (not spec authority, useful for a second opinion on the
same spec):
[cmaneu/fabric-open-mirroring-sample](https://github.com/cmaneu/fabric-open-mirroring-sample),
[serverlesssql.com — Exploring Open Mirroring](https://www.serverlesssql.com/exploring-open-mirroring-in-microsoft-fabric/).

## What this connector implements

```
fabric_open_mirroring_iris/
  iris_types.py    IRIS SQL type name -> Arrow/Parquet type mapping
  source.py        IrisSource abstraction: FakeIrisSource (tests) + IrisDbApiSource (real, iris DB-API)
  landing_zone.py  Open Mirroring file/metadata writer (the spec implementation)
  publisher.py     Orchestration: snapshot + incremental batches, crash-safe sequencing
  state.py         Local publisher bookkeeping (NOT part of the landing zone itself)
```

### Landing zone layout produced

```
<landing-zone-root>/
  _partnerEvents.json                  # optional, mirrored-database level
  Patient/
    _metadata.json                     # {"keyColumns": ["PatientID"]}
    00000000000000000001.parquet       # __rowMarker__ absent -> initial-load inserts,
                                        # OR present with value 4 (Upsert) -- see below
    00000000000000000002.parquet       # incremental batch, __rowMarker__ last column
  dbo.schema/Encounter/
    _metadata.json
    00000000000000000001.parquet
```

### Row-level change semantics

| IRIS-side event | `__rowMarker__` written | Why |
| --- | --- | --- |
| Initial snapshot row | `4` (Upsert) by default; `TableConfig(idempotent_snapshot=False)` omits the column for plain Insert semantics | Upsert makes a re-run after a crash a no-op instead of a duplicate row (see "Design decisions") |
| Source INSERT | `4` (Upsert) | Same idempotency reasoning — an at-least-once re-send must not duplicate |
| Source UPDATE | `4` (Upsert) | Matches spec requirement that updates carry the full row |
| Source DELETE | `2` (Delete) | Only marker that removes a row by key |

### Type mapping (see `fabric_open_mirroring_iris/iris_types.py`)

| IRIS SQL type | Arrow/Parquet type |
| --- | --- |
| `BIGINT` | `int64` |
| `INTEGER` / `INT` | `int32` |
| `SMALLINT` | `int16` |
| `TINYINT` | `int8` |
| `NUMERIC` / `DECIMAL` | `decimal128(precision, scale)` from `INFORMATION_SCHEMA.COLUMNS`; falls back to `decimal128(38, 10)` if precision/scale weren't introspected |
| `DOUBLE` / `FLOAT` | `float64` |
| `REAL` | `float32` |
| `CHAR` / `VARCHAR` / `LONGVARCHAR` / `NVARCHAR` | `string` (`utf8`) |
| `DATE` | `date32` — deliberately not `date64`, to match the logical=DATE/physical=INT32 pairing the landing-zone spec calls out as required |
| `TIME` | `time64('us')` |
| `TIMESTAMP` / `TIMESTAMP2` | `timestamp('us')` |
| `BIT` / `BOOLEAN` | `bool` |
| `VARBINARY` / `LONGVARBINARY` / `BINARY` / `IMAGE` | `binary` |
| `GUID` / `UNIQUEIDENTIFIER` | `string` |
| `JSON` | `string` |
| anything else not listed | `string` (conservative fallback — never silently dropped) |

**Deliberately dropped, not mapped** (raises `UnsupportedIrisTypeError` by
default; `iris_schema_to_arrow(..., skip_unsupported=True)` to skip instead
of raise):

- **IRIS `%List`-encoded columns** (`$LISTBUILD` binary storage). Not a
  scalar SQL value; must be projected through `$LISTTOSTRING`/`$LISTGET` in
  the extraction SQL before this connector can carry it.
- **Embedded object / relationship-valued (OREF) columns.** Not scalar SQL
  values; a plain `SELECT *` does not project them 1:1 into a column this
  connector can put in a Parquet file.

`INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` name spellings above are based on
general IRIS SQL documentation knowledge and **were not re-verified against
docs.intersystems.com in this session** (that domain is blocked by this
sandbox's egress proxy — see `STATUS.md`). Verify the exact set of type
names your IRIS version reports before trusting this table in production.

## Design decisions

1. **Sequence numbers are derived by scanning the landing-zone directory**
   (`OpenMirroringLandingZoneWriter.next_sequence_number`), not from local
   state. A crashed-and-restarted publisher is self-healing: it always
   continues the real on-disk sequence, and never reuses or skips a number,
   even if its own bookkeeping was stale or missing.
2. **Files are written to a `_<name>.tmp` path and then `os.replace`d into
   place** — the same temp-file-then-atomic-rename pattern Microsoft's own
   `onelake-apis-in-action` sample uses, applied to a local filesystem here
   since there is no live OneLake endpoint to write against in this
   environment.
3. **Upsert (4), not Insert (0), for both snapshot rows and incremental
   insert/update rows** (see table above). Microsoft's docs say plain
   Insert is the *recommended* choice for initial-load performance because
   it skips duplicate validation — this connector trades a small amount of
   that performance for a strong idempotency guarantee: an at-least-once
   re-send of the same batch (the failure mode a crash between "file
   written" and "local state saved" produces) becomes a no-op instead of a
   duplicate row. `TableConfig(idempotent_snapshot=False)` opts back into
   plain-Insert initial loads for callers who can guarantee exactly-once
   execution some other way (e.g., an idempotent workflow engine).
4. **Local publisher state lives outside the landing zone**
   (`fabric_open_mirroring_iris/state.py`), so the mirroring engine never
   sees it as a stray file inside a table folder. State is saved only
   *after* the corresponding data file is durably renamed into place, so a
   crash can only cause an at-least-once re-send, never data loss or a
   corrupted/reused sequence number. See
   `tests/test_publisher.py::test_rerun_after_crash_before_state_save_does_not_corrupt_sequence`.
5. **Delete rows carry the key columns plus NULL for every other column**
   (rather than guessing stale values), which requires relaxing non-key
   columns to nullable in the incremental file's Arrow schema even when the
   source IRIS column is `NOT NULL`
   (`landing_zone.relax_nullability_for_incremental`). Whether Fabric's
   spec actually *requires* full column data on a delete row (as it does
   for updates) could not be pinned down from the pages fetched in this
   session — flagged UNVERIFIED in `STATUS.md`.
6. **Change-data-capture from IRIS is an application-level convention, not
   something IRIS provides generically over SQL.** `IrisDbApiSource`
   implements a watermark-column + optional soft-delete-column strategy;
   true hard-delete capture needs IRIS journal mining or a trigger-
   maintained change-log table, neither of which is implemented here. See
   the docstring in `fabric_open_mirroring_iris/source.py` and
   `PUBLISHING.md`.

## Running the tests

```bash
cd connectors/fabric-open-mirroring-iris
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v
```

No IRIS, no Docker, no Fabric tenant, no network access needed — the whole
suite runs against `FakeIrisSource` and a local temp directory standing in
for the OneLake landing zone (per this repo's `careconnect-sdoh/evals`
offline-test model, and the hard rule in this task that no vendor endpoint
may be contacted). 47 tests, all passing as of this writing — see
`STATUS.md` for the pasted run.

## Using it against a real IRIS instance (not exercised in this session)

```python
import iris  # pip install intersystems-irispython
from fabric_open_mirroring_iris import (
    FabricOpenMirroringPublisher, TableConfig, PublisherState,
    OpenMirroringLandingZoneWriter,
)
from fabric_open_mirroring_iris.source import IrisDbApiSource, ChangeTrackingConfig

conn = iris.connect("localhost", 1972, "USER", "_SYSTEM", "SYS")
source = IrisDbApiSource(
    conn,
    change_tracking={
        "Patient": ChangeTrackingConfig(
            watermark_column="LastModified", soft_delete_column="IsDeleted"
        )
    },
)
writer = OpenMirroringLandingZoneWriter("/path/to/synced/OneLake/LandingZone")
state = PublisherState("/var/lib/fabric-open-mirroring-iris/state.json")
publisher = FabricOpenMirroringPublisher(source, writer, state)

cfg = TableConfig(table_name="Patient", key_columns=["PatientID"])
publisher.publish_initial_snapshot(cfg)
publisher.publish_changes(cfg)  # run on a schedule
```

`writer`'s root directory must ultimately be uploaded to
`https://onelake.blob.fabric.microsoft.com/<workspace>/<mirrored-db>/Files/LandingZone/`
using the OneLake Blob or ADLS Gen2 API (see the `onelake-apis-in-action`
citation above) — this connector writes the local files; the upload leg to
an actual Fabric tenant is out of scope for this sandbox (no Azure
credentials, no network path to any Azure endpoint, and this task's hard
rules forbid attempting one).

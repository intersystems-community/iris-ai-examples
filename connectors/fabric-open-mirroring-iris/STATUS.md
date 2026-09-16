# STATUS

## VERIFIED

**Open Mirroring is real, current, and partner-buildable with no Microsoft
dependency.** Fetched read-only from Microsoft's own docs source
(`raw.githubusercontent.com/MicrosoftDocs/fabric-docs`, the repository
`learn.microsoft.com/en-us/fabric/mirroring/...` is published from — no
`learn.microsoft.com`, `onelake.*`, or any other Azure/Microsoft endpoint
was contacted; `learn.microsoft.com` itself returned
`EGRESS_BLOCKED` in this sandbox when tried directly):

- `open-mirroring.md`: "Open mirroring enables any application to write
  change data directly into a mirrored database in Fabric... based on the
  open Delta Lake table format."
- `overview.md` native-sources include file
  (`mirrored-sources-table.md`): current list is Azure SQL Database, Azure
  SQL Managed Instance, Azure Cosmos DB, Azure Databricks, Azure Database
  for PostgreSQL, Azure Database for MySQL (preview), Snowflake, SQL
  Server, Oracle, SAP, Google BigQuery, Dremio catalog (preview),
  SharePoint List (preview), Open mirrored databases, Fabric SQL database.
  **InterSystems IRIS is not on this list**, confirmed directly rather
  than assumed from the task's framing.
- `open-mirroring-landing-zone-format.md`: full landing-zone spec —
  `Files/LandingZone/<table>/` (or `<Schema>.schema/<table>/`) path shape;
  required `_metadata.json` with immutable `keyColumns`; optional-but-
  recommended `_partnerEvents.json` at the mirrored-database level; 20-digit
  zero-padded, strictly-increasing `NNNNNNNNNNNNNNNNNNNN.parquet` file
  names; `__rowMarker__` as the required-last incremental control column
  with codes 0=Insert/1=Update/2=Delete/4=Upsert; `__rowMarker__` optional
  and not recommended on the initial load; add/drop/rename/retype column
  rules; cleanup into `_ProcessedFiles`/`_FilesReadyToDelete` after 7 days.
- `onelake-apis-in-action.md`: OneLake Blob endpoint
  `onelake.blob.fabric.microsoft.com`, `DefaultAzureCredential`-based auth,
  temp-file-then-atomic-rename write pattern — this connector's
  `os.replace`-based local write in `landing_zone.py` mirrors that pattern.

Exact URLs for every claim above are tabulated in `README.md` "Spec
citations".

**All 47 tests pass, on real installed dependencies, in this sandbox, just
now:**

```
$ python -m pytest -v
...
============================== 47 passed in 0.14s ==============================
```

```
$ pip freeze | grep -Ei "pyarrow|pytest|intersystems"
intersystems_irispython==5.4.0
pyarrow==25.0.1
pytest==9.1.1
```
(Python 3.11.15; full pip install transcripts for `pyarrow`, `pytest`, and
`intersystems-irispython` were captured live during this build — all three
installed cleanly from PyPI with no errors.)

Tests cover, against `FakeIrisSource` and a local temp directory (no IRIS,
no Docker, no Fabric tenant, no network — same offline model as
`careconnect-sdoh/evals`):
- `_metadata.json` contents and immutability of `keyColumns`
  (`test_landing_zone_writer.py`).
- `_partnerEvents.json` contents.
- 20-digit filename pattern, strict sequence monotonicity across multiple
  batches, no leftover `.tmp` files after a write.
- Every written Parquet file is read back with `pyarrow.parquet.read_table`
  and its schema/contents asserted exactly.
- `__rowMarker__` required-last-column and initial-load-must-not-have-it
  validation.
- End-to-end insert/update/delete semantics, replayed through a
  spec-following simulator (`tests/mirror_simulator.py`) to assert the
  *resulting* row-set is correct, not just that files were written.
- **Re-run/idempotency**: `test_rerun_after_crash_before_state_save_does_not_corrupt_sequence`
  simulates a crash between a file being durably written and local state
  being persisted, then re-runs; asserts the sequence is never reused or
  overwritten and the replayed end state is still correct.
  `test_rerun_after_full_process_restart_resumes_snapshot_offset` and
  `test_snapshot_is_not_redone_once_marked_done` cover a clean restart with
  no changes.
- Type mapping table (`test_type_mapping.py`), including the DATE ->
  `date32` (not `date64`) choice and the two explicitly-unsupported IRIS
  types raising a descriptive error.

**The certified InterSystems IRIS Power BI connector exists** and is
InterSystems's own precedent for a Microsoft-certified integration:
confirmed via web search hits on InterSystems's own press release
(intersystems.com/news, April 2019) and the InterSystems Developer
Community. Cited in `PUBLISHING.md`.

**pyarrow's Parquet writer, not this connector, is responsible for
logical/physical type-combination validity** — verified by inspection of
`landing_zone.py`'s use of `pyarrow.parquet.write_table` (no hand-built
Parquet footers) and by the passing `test_date_maps_to_date32_not_date64`
test.

## UNVERIFIED

- **Exact placement of `_partnerEvents.json`** ("mirrored database level,
  not per table") — the fetched spec page states this but this session
  could not confirm whether that means the `LandingZone/` root (what this
  connector implements) or one level up at the mirrored database's `Files/`
  root. Needs a live Fabric workspace or a closer look at the tutorial
  walkthrough to pin down.
- **Whether a delete row must carry full non-key column data**, the way an
  update row explicitly must per the spec. This connector fills non-key
  columns with NULL on delete and relaxes their nullability accordingly
  (`landing_zone.relax_nullability_for_incremental`) — a defensible but
  unconfirmed choice.
- **The IRIS SQL data type name spellings** in `iris_types.py`'s mapping
  table (`BIGINT`, `VARCHAR`, `NUMERIC`, etc., as they'd appear in
  `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`) — based on general IRIS SQL
  documentation knowledge, not re-verified against docs.intersystems.com in
  this session (`docs.intersystems.com` returned `EGRESS_BLOCKED` when
  fetched directly). Verify against a live IRIS instance or the IRIS SQL
  Reference before trusting this table in production.
- **End-to-end behavior against a real OneLake landing zone and a real
  Fabric mirrored database** — nothing in this session touched OneLake,
  Azure, or any Fabric tenant (none exists in this environment, and the
  task's hard rules forbid attempting to reach one). Everything above is
  verified against the *documented* spec and against this connector's own
  test suite, not against Fabric's actual server-side behavior.
- **`IrisDbApiSource` (the real, non-Fake IRIS adapter)** compiles and
  imports cleanly (`python -m py_compile` succeeded, shown above) and its
  SQL is written against documented IRIS SQL (`INFORMATION_SCHEMA.COLUMNS`,
  `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`), but it has never executed
  against a live IRIS instance — there is none in this environment. Its
  DB-API driver import (`import iris` from `intersystems-irispython==5.4.0`)
  does succeed.
- **The watermark/soft-delete change-tracking convention** is a documented
  design assumption (see `source.py` module docstring), not a feature IRIS
  provides out of the box; whether it fits any particular real IRIS schema
  depends on that schema already maintaining a watermark column (and
  optionally a soft-delete column), which is a per-deployment integration
  task, not something this connector can supply generically.
- **The "Create mirrored database" REST API** and the
  `open-mirroring-tutorial` walkthrough were found via search but not
  fetched and read in full in this session — cited in `README.md` as
  "referenced but not fetched," not relied on for any code or test claim.
- **True hard-delete capture via IRIS journaling** is not implemented and
  was not researched beyond noting it exists as a documented IRIS concept
  (journaling) — flagged as future work in `PUBLISHING.md`/`README.md`,
  not something this session evaluated for feasibility.

## HUMAN ACTIONS REQUIRED

1. **Verify the IRIS SQL type-name mapping table** in `iris_types.py`
   against a real IRIS instance's `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`
   output (or the IRIS SQL Reference on docs.intersystems.com, unreachable
   from this sandbox) before using this connector against production IRIS
   tables.
2. **Confirm `_partnerEvents.json` placement** against a real Fabric
   workspace (create an open mirrored database, inspect the landing zone
   URL Fabric hands back) or a full read of the tutorial page — this
   session's fetched pages left it ambiguous.
3. **Build and test the actual OneLake upload transport.** This connector
   produces the correct local file tree; getting it into OneLake requires
   Azure/Fabric credentials (a service principal with access to the target
   workspace) and calling the Blob or ADLS Gen2 API against
   `onelake.blob.fabric.microsoft.com` — nothing in this session has those
   credentials or that network path, and the task's hard rules forbid
   attempting it here.
4. **Decide and implement a real IRIS change-tracking mechanism** for each
   production table: either retrofit a watermark column (+ optional
   soft-delete column) as this connector's `IrisDbApiSource` expects, or
   invest in IRIS-journal-based CDC for true hard-delete capture without an
   application-level convention.
5. **Run the full suite against a live Fabric tenant end-to-end** (create
   an open mirrored database, point this connector's writer at its landing
   zone, upload, and confirm in the Fabric portal that the mirrored table
   matches expectations) before calling this production-ready. Nothing in
   `UNVERIFIED` above can be closed without that tenant.
6. **If pursuing Route 2 in `PUBLISHING.md`** (native mirrored source
   status), that requires a business-development / partner-engineering
   conversation with Microsoft's Fabric team — outside the scope of what
   any code change in this repo can accomplish.

# STATUS

Verification ceiling for this directory (per `../README.md`): **no running
IRIS instance, no Docker daemon, no Fivetran account, no third-party
submissions** were available or used in this session. Every command below
was actually run in this environment; output is pasted verbatim (only
`JAVA_TOOL_OPTIONS`/proxy-config noise lines were stripped from the
`fivetran debug` output for length -- nothing else was edited or
reordered).

## VERIFIED

**Every dependency actually installs, from a clean venv, with no
conflicts:**

```
$ python3 -m venv venv && source venv/bin/activate
$ pip install -r requirements.txt
Successfully installed asttokens-3.0.2 attrs-26.1.0 beautifulsoup4-4.15.0 bleach-6.4.0 certifi-2026.7.22 cffi-2.1.1 charset_normalizer-3.5.1 cryptography-49.0.0 defusedxml-0.7.1 docopt-0.6.2 executing-2.2.1 fastjsonschema-2.22.2 fivetran-connector-sdk-2.12.1 grpcio-1.80.0 grpcio-tools-1.80.0 idna-3.19 intersystems-irispython-5.4.0 ipython-9.17.1 ipython-pygments-lexers-1.1.1 jedi-0.20.0 jinja2-3.1.6 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 jupyter-client-8.10.0 jupyter-core-5.9.1 jupyterlab-pygments-0.3.0 markupsafe-3.0.3 matplotlib-inline-0.2.2 mistune-3.3.4 nbclient-0.11.0 nbconvert-7.17.1 nbformat-5.11.1 packaging-26.3 pandocfilters-1.5.1 parso-0.8.7 pathspec-1.1.1 pexpect-4.9.0 pipreqs-fivetran-1.1.2 platformdirs-4.11.8 prompt-toolkit-3.0.53 protobuf-6.33.6 psutil-7.2.2 ptyprocess-0.7.0 pure-eval-0.2.4 pycparser-3.0 pygments-2.21.0 python-dateutil-2.9.0.post0 pyzmq-27.2.0 referencing-0.37.0 requests-2.34.2 rpds-py-2026.6.3 six-1.17.0 soupsieve-2.9.2 stack_data-0.6.3 tinycss2-1.5.1 tornado-6.5.10 tqdm-4.70.0 traitlets-5.16.1 typing-extensions-4.16.0 urllib3-2.8.0 wcwidth-0.8.3 webencodings-0.6.1 yarg-0.1.10

$ pip check
No broken requirements found.

$ pip show fivetran-connector-sdk | grep -E "^(Name|Version)"
Name: fivetran_connector_sdk
Version: 2.12.1
$ pip show intersystems-irispython | grep -E "^(Name|Version)"
Name: intersystems_irispython
Version: 5.4.0
```

**The full test suite passes, offline, on that same clean install:**

```
$ pip install pytest
$ python -m pytest tests/ -q
...................s.................................................... [ 94%]
....                                                                     [100%]
75 passed, 1 skipped in 0.25s
```

75 tests pass; 1 is an intentional `pytest.skip` (an empty-string port
value means "use the default," tested elsewhere, not an error case).
Coverage, by file: `test_config.py` (required fields, type/range
validation, `cursor_fields` JSON parsing -- 17 cases), `test_type_mapping.py`
(every IRIS type this connector maps, dropped types, NUMERIC
precision/scale clamping, unrecognized-type fallback -- 26 cases),
`test_catalog.py` (schema() output shape, dropped-column exclusion,
primary-key detection, `INFORMATION_SCHEMA`-shaped fake queries -- 7 cases),
`test_sync_incremental.py` / `test_sync_full_refresh.py` /
`test_checkpoint_resume.py` (upsert emission, cursor advancement, and the
explicit interrupted-sync-then-resume path, at both the per-table and the
whole-`run_sync` level, using a `RecordingOperations` fake that can raise
mid-sync on command -- 15 cases), `test_db.py` (the `DBConnection` protocol,
and `db.connect()`'s `RuntimeError` when the `iris` package is absent),
`test_connector_entrypoint.py` (the actual `connector.py` file, not just
`iris_connector/`; skipped automatically if `fivetran_connector_sdk` is not
installed).

**`fivetran debug` runs successfully, fully offline, against the real
connector code** (not a toy), using `iris_connector.fake_db` in place of a
live IRIS instance (`configuration.json`'s `"driver": "fake"`). This
required no credentials and no IRIS; it did require one outbound download
(the SDK's own Java-based "connector tester," ~244MB, from Fivetran's own
CDN) which this environment's egress proxy allowed.

First run, from empty state (only the noisiest proxy/JVM lines stripped):

```
$ fivetran debug --configuration configuration.json
...
previous state:
                                   {}
...
calling schema()
09:11:35.331 WARNING  ⚡ connector PATIENT.CHART_NOTE: IRIS type LONGVARCHAR is not synced by this connector (see type_mapping.DROPPED_TYPES / README.md); column dropped.
                                   schema change detected: tester.encounter
                                   table created: tester.encounter
                                   schema change detected: tester.patient
                                   table created: tester.patient
...
calling update()
                                   checkpoint recorded: {"tables": {"ENCOUNTER": {"cursor_value": "2026-02-03 14:15:00.000000"}}}
                                   table truncated: tester.patient
                                   checkpoint recorded: {"tables": {"ENCOUNTER": {"cursor_value": "2026-02-03 14:15:00.000000"}, "PATIENT": {"truncated": true, "resume_after_pk": null}}}
                                   checkpoint recorded: {"tables": {"ENCOUNTER": {"cursor_value": "2026-02-03 14:15:00.000000"}, "PATIENT": {"truncated": true, "resume_after_pk": 2}}}
                                   checkpoint recorded: {"tables": {"ENCOUNTER": {"cursor_value": "2026-02-03 14:15:00.000000"}, "PATIENT": {"truncated": false, "resume_after_pk": null}}}
                                   Final checkpoint: committing any remaining operations
SYNC SUCCEEDED — total elapsed 00:00:01
                                   Operation       | Counts
                                   ----------------+------------
                                   Upserts         | 4
                                   Updates         | 0
                                   Deletes         | 0
                                   Truncates       | 1
                                   Schema changes  | 2
                                   Checkpoints     | 4
                                   File uploads    | 0
```

Second run immediately after, re-reading the state `fivetran debug`
persisted to `files/state.json` from the first run:

```
$ fivetran debug --configuration configuration.json
...
previous state:
                                   {"tables": {"ENCOUNTER": {"cursor_value": "2026-02-03 14:15:00.000000"}, "PATIENT": {"truncated": false, "resume_after_pk": null}}}
...
SYNC SUCCEEDED — total elapsed 00:00:01
                                   Operation       | Counts
                                   ----------------+------------
                                   Upserts         | 3
                                   Truncates       | 1
                                   Checkpoints     | 4
```

3 upserts on the second run, not 4, is exactly the designed behavior: the
incremental `ENCOUNTER` table only re-emits the one row at its saved
cursor value (idempotent, per README.md), and the full-refresh `PATIENT`
table truncates and reloads both its rows again, every cycle, by design.

**The resulting synced data is correct**, read back from the debug run's
own DuckDB destination:

```
$ python3 -c "
import duckdb
con = duckdb.connect('files/warehouse.db', read_only=True)
for row in con.execute('select patient_id, name, birth_date, last_updated, height_cm, is_active from tester.patient order by patient_id').fetchall():
    print(row)
for row in con.execute('select encounter_id, patient_id, visit_at, note from tester.encounter order by encounter_id').fetchall():
    print(row)
"
(1, 'Ada Lovelace', datetime.date(1815, 12, 10), datetime.datetime(2026, 1, 1, 8, 0), Decimal('163.0'), True)
(2, 'Alan Turing', datetime.date(1912, 6, 23), datetime.datetime(2026, 1, 2, 9, 30), Decimal('179.5'), True)
(1, 1, datetime.datetime(2026, 2, 1, 10, 0, tzinfo=<StaticTzInfo 'Etc/UTC'>), 'annual checkup')
(2, 2, datetime.datetime(2026, 2, 3, 14, 15, tzinfo=<StaticTzInfo 'Etc/UTC'>), 'follow-up')
```

`height_cm` landed as `DECIMAL(5,1)` (confirmed via `describe tester.patient`
during this session), `visit_at` landed as `TIMESTAMP WITH TIME ZONE` at
the correct UTC instant, `CHART_NOTE` (the `LONGVARCHAR`/stream column) is
correctly absent from the destination schema entirely, and `PATIENT_ID` is
the primary key (confirmed via `describe`, `'PRI'`).

**A real bug was found and fixed by actually running `fivetran debug`**,
not found by inspection: the first draft of this connector failed with

```
ValueError: time data '2026-02-01T10:00:00.000000' does not match format '%Y-%m-%dT%H:%M:%S.%f%z'
```

because `fivetran_connector_sdk`'s `UTC_DATETIME` parser requires a
timezone offset in the string, and IRIS's documented ODBC-mode formatting
of `%Library.PosixTime` (`YYYY-MM-DD HH:MM:SS.FFFFFF`) has none. Fixed in
`iris_connector/type_mapping.coerce_value_for_upsert()`, applied to every
upserted value in `iris_connector/sync.py`. Full writeup in
`README.md`'s "The `POSIXTIME` -> `UTC_DATETIME` fix" section.

**`iris.connect()`'s call signature matches the DB-API facts this task
specified**, confirmed by reading the installed `intersystems-irispython`
5.4.0 package directly (`iris.connect.__doc__`, `iris.dbapi.apilevel`,
`iris.dbapi.paramstyle`): `iris.connect(hostname, port, namespace,
username, password, timeout=..., ...)`, `paramstyle = "qmark"` (`?`
placeholders, which `iris_connector/catalog.py` and `sync.py` use
throughout), `apilevel = "2.0"`.

**IRIS's `INFORMATION_SCHEMA` shape used by `catalog.py` is documented,
not assumed-ANSI**, per InterSystems' own documentation and Developer
Community, found via `WebSearch` (`docs.intersystems.com` itself is
blocked by this environment's egress proxy, so these are `WebSearch`'s
summaries of that documentation, not a direct fetch):
`INFORMATION_SCHEMA.COLUMNS.PRIMARY_KEY` is a direct `YES`/`NO` column
InterSystems adds to `COLUMNS` (not the ANSI `KEY_COLUMN_USAGE` join);
`INFORMATION_SCHEMA.TABLES.TABLE_TYPE = 'BASE TABLE'` excludes views/system
tables (an exact community-post-confirmed query); the ODBC/JDBC `DATA_TYPE`
vocabulary (`BIGINT, BIT, DATE, DOUBLE, GUID, INTEGER, LONGVARBINARY,
LONGVARCHAR, NUMERIC, OREF, POSIXTIME, SMALLINT, TIME, TIMESTAMP, TINYINT,
VARBINARY, VARCHAR`) that `type_mapping.py` is built against.

**The Fivetran publishing landscape claims in `PUBLISHING.md` are sourced,
not invented**: `fivetran/community_connectors`'s README and
CONTRIBUTING.md were fetched in full (`raw.githubusercontent.com`, not
blocked); the Partner-Built program's "not accepting new partners at this
time" status, its Private-Preview/Beta/GA timeline, and the separate
By-Request program were found via `WebSearch` summaries of
`fivetran.com`'s own docs (direct fetch of `fivetran.com` is also blocked
by this environment's egress proxy).

## UNVERIFIED

Everything below needs a live IRIS instance, and some of it a real
Fivetran account, neither of which exist in this environment:

- **The entire real-connection path** (`iris_connector/db.py`'s
  `connect()`) has never executed against a real IRIS server. Only its
  *call shape* was checked against the installed driver's own docstring.
- **Every `INFORMATION_SCHEMA` fact** `catalog.py` depends on
  (`PRIMARY_KEY` column, `TABLE_TYPE = 'BASE TABLE'`, the exact
  `DATA_TYPE` strings, `CHARACTER_MAXIMUM_LENGTH`/`NUMERIC_PRECISION`/
  `NUMERIC_SCALE` semantics) is sourced from InterSystems' documentation
  and Developer Community via `WebSearch`, never run against a real
  namespace. In particular: does a table with no explicit primary key
  constraint (common in freeform/legacy IRIS classes) report
  `PRIMARY_KEY = 'NO'` for every column, or omit rows, or something else?
- **Whether the DB-API driver actually returns Python `None` for SQL
  `NULL`** (assumed standard PEP 249 behavior; `sync.py`/`type_mapping.py`
  rely on this and have no fallback).
- **The `POSIXTIME` -> `UTC_DATETIME` fix's core assumption**: that the
  driver's ODBC-mode string for `%Library.PosixTime` is *always* the UTC
  wall clock with no server-timezone skew, on every supported IRIS
  version. This was fixed against the SDK's documented parser requirements
  and IRIS's documented formatting behavior, but never against an actual
  `%PosixTime` column round-tripping through a live driver.
- **Whether a `LONGVARCHAR`/`LONGVARBINARY` (stream) column, if a future
  iteration decided to sync it, actually errors the way IRIS's own
  documentation says** (`SQLCODE -37` on use in `WHERE`/most functions) --
  taken from documentation, not exercised.
- **Whether `%Boolean`/`BIT` columns always come back as Python `int`
  `0`/`1`** over this driver (observed to work in the fake-driven
  `fivetran debug` run above, where the fake returns exactly that -- not
  confirmed against the real driver).
- **Behavior at real-world scale**: batch sizing, checkpoint frequency,
  and memory behavior with thousands/millions of rows, wide tables, or
  many concurrent tables. The fake dataset is deliberately tiny (2 tables,
  2-5 rows each) -- enough to prove the *logic*, not the *scale*.
- **`fivetran deploy`** (as opposed to `debug`) was not run: it requires a
  real Fivetran destination, group, connection name, and API deploy key --
  a real Fivetran account, which this session does not have and was told
  not to create.
- **Everything in `PUBLISHING.md`'s "Recommendation"/"Who must own it"
  sections** is this session's analysis of sourced facts, not something
  Fivetran or InterSystems confirmed directly to this session.

## HUMAN ACTIONS REQUIRED

1. **Get a live IRIS instance** (any recent version with SQL enabled) and
   run this connector's `schema()`/`update()` against a real
   `iris_connector.db.connect()` connection, with at least one table
   containing each of: a `%Library.PosixTime` column, a `%Stream.*`
   column, a `NUMERIC` column with explicit precision/scale, a table with
   no primary key, and a table with a composite primary key. Confirm every
   item in UNVERIFIED above, then update this file.
2. **Fix or confirm the `%Boolean` assumption** and the `POSIXTIME`
   formatting assumption specifically -- these are the two places this
   connector already had to patch behavior discovered only by actually
   running code, so they are the most likely places a real IRIS instance
   still surprises it.
3. **Get (or use an existing) Fivetran account** to run `fivetran deploy`
   for real, and to open a PR to `fivetran/community_connectors` per
   `PUBLISHING.md` #2 -- ideally from an account/identity that reads as
   InterSystems, not an individual, given the PR is reviewed by a single
   Fivetran maintainer.
4. **Loop in an ISC Alliances/partnerships contact for Fivetran** before
   any public PR or announcement, per `PUBLISHING.md`'s "Who at
   InterSystems must own it" -- both to ask about the closed Partner-Built
   program's exception path, and to be the named contact if Fivetran's
   reviewer has questions.
5. **Decide this directory's final home** -- per `../README.md`'s
   placement caveat, this is staged work, and a real connector belongs in
   its own repo with its own release cadence and CI, not in
   `iris-ai-examples`.
6. **Re-run `fivetran debug` before any deploy**, every time -- it is
   fast, free, needs no credentials, and already caught one real bug in
   this codebase (see VERIFIED). There is no reason to skip it.

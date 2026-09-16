# STATUS

Read this before trusting any claim in `README.md`/`PUBLISHING.md`. Per
`../README.md` "Verification ceiling in this environment": **no running IRIS
instance and no Docker daemon exist in this environment.** Everything below is
either something that was actually run (with real, pasted output) or explicitly
flagged as not run.

## VERIFIED (claims backed by real, pasted command output)

### Dependencies actually install

```
$ pip install "airbyte-cdk==7.28.4"
...
Successfully installed Jinja2-3.1.6 MarkupSafe-3.0.3 PyYAML-6.0.3 airbyte-cdk-7.28.4
airbyte-protocol-models-dataclasses-0.17.1 annotated-types-0.8.0 anyascii-0.3.3
attributes-doc-0.5.0 attrs-26.1.0 backoff-2.2.1 boltons-25.0.0 bracex-3.0.1
cachetools-7.1.8 cattrs-26.2.0 certifi-2026.7.22 cffi-2.1.1
charset_normalizer-3.5.1 click-8.5.0 cloudpickle-3.1.2 cryptography-50.0.1
dateparser-1.4.3 dpath-2.2.0 dunamai-1.26.2 genson-1.3.0 google-api-core-2.37.0
google-auth-2.58.0 google-cloud-secret-manager-2.30.0
googleapis-common-protos-1.75.3 grpc-google-iam-v1-0.14.5 grpcio-1.84.0
grpcio-status-1.84.0 idna-3.19 ijson-3.5.1 isodate-0.6.1 joblib-1.6.0
jsonref-1.1.0 jsonschema-4.26.0 jsonschema-specifications-2025.9.1
markdown-it-py-4.2.0 mdurl-0.1.2 nltk-3.9.4 numpy-2.4.6 opentelemetry-api-1.44.0
orjson-3.12.0 packaging-26.3 pandas-2.2.3 platformdirs-4.11.8 proto-plus-1.28.4
protobuf-7.36.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.5
pydantic-core-2.46.5 pygments-2.21.0 pyjwt-2.14.0 pyrate-limiter-3.1.1
python-dateutil-2.9.0.post0 python-ulid-3.2.1 pytz-2026.3.post1
rapidfuzz-3.14.6 referencing-0.37.0 regex-2026.9.10 requests-2.34.2
requests_cache-1.3.3 rich-15.0.0 rich-click-1.9.9 rpds-py-2026.6.3
setuptools-80.10.2 six-1.17.0 tqdm-4.70.1 typing-extensions-4.16.0
typing-inspection-0.4.4 tzdata-2026.4 tzlocal-5.4.4 unidecode-1.4.0
url-normalize-3.0.0 urllib3-2.8.0 wcmatch-10.0 whenever-0.8.10 xmltodict-0.14.2

$ pip install intersystems-irispython sqlalchemy-iris
...
Successfully installed SQLAlchemy-2.0.54 greenlet-3.5.6
intersystems-irispython-5.3.2 iris-embedded-python-wrapper-0.6.1 sqlalchemy-iris-0.20.0
```

`pip freeze` in the working environment: `airbyte-cdk==7.28.4`,
`intersystems_irispython==5.3.2`, `sqlalchemy-iris==0.20.0`, `jsonschema==4.26.0`,
`pytest==9.1.1`. Python 3.11.15.

### `intersystems-irispython`'s real DB-API module exists and behaves as documented

```
>>> import iris.dbapi as dbapi
>>> [n for n in dir(dbapi) if not n.startswith('_')]
['BINARY', 'Binary', 'Cursor', 'DATETIME', 'DataError', 'DataRow', 'DatabaseError',
 'Date', 'DateFromTicks', 'Error', 'IntegrityError', 'InterfaceError', 'InternalError',
 'NUMBER', 'NotSupportedError', 'OperationalError', 'ProgrammingError', 'ROWID',
 'SQLType', 'STRING', 'Time', 'TimeFromTicks', 'Timestamp', 'TimestampFromTicks',
 'Warning', 'apilevel', 'connect', 'datetime', 'enum', 'iris', 'paramstyle', 'threadsafety']
>>> dbapi.apilevel, dbapi.paramstyle, dbapi.threadsafety
('2.0', 'qmark', 1)
>>> [m for m in dir(dbapi.Cursor) if not m.startswith('_')]
['arraysize', 'callproc', 'close', 'description', 'direct_execute', 'execute',
 'executemany', 'fetchall', 'fetchmany', 'fetchone', 'isClosed', 'lastrowid',
 'nextset', 'rowcount', 'scroll']
```

This confirms `paramstyle == "qmark"` (i.e. `?` placeholders, used throughout
`iris_client.py`) directly against the installed package, not just documentation.

### `check` against the real driver fails cleanly on an unreachable host (no live IRIS needed to prove this much)

```
$ python -m source_iris.run check --config /tmp/real_config.json   # host=127.0.0.1:51972, nothing listening
{"type":"LOG","log":{"level":"WARN","message":"IRISINSTALLDIR or ISC_PACKAGE_INSTALLDIR environment variable is not set"}}
{"type":"LOG","log":{"level":"WARN","message":"Embedded Python not configured; call iris.connect(path=...) to configure it"}}
{"type":"LOG","log":{"level":"ERROR","message":"Check failed"}}
{"type":"CONNECTION_STATUS","connectionStatus":{"status":"FAILED","message":"'<COMMUNICATION LINK ERROR> Failed to connect to server; Details: Error code: -1 Error message: '"}}
```

This proves `source_iris/db.py::connect_real_iris` actually calls the real
`iris.dbapi.connect(...)` (not the fake) end to end through the real CLI
(`python -m source_iris.run`), and that `IrisSource.check_connection`'s
try/except correctly turns a real driver exception into a `FAILED`
`AirbyteConnectionStatus` rather than crashing. It does **not** prove a
successful connection or anything about `discover`/`read` against a real
table — there is nothing listening on that port to connect to.

### `spec` via the real CLI

```
$ python -m source_iris.run spec
{"type":"SPEC","spec":{"connectionSpecification":{"$schema":"http://json-schema.org/draft-07/schema#","title":"InterSystems IRIS Source Spec","type":"object","required":["host","port","namespace","username","password"], ...
```
Full output matches `source_iris/spec.yaml`, loaded through
`BaseConnector.spec()` (the CDK's own spec-loading code path).

### Full pytest suite: 72/72 passed, offline, no Docker, no live IRIS

```
$ python -m pytest -v --durations=10
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- .../venv/bin/python
cachedir: .pytest_cache
rootdir: /home/user/iris-ai-examples/connectors/airbyte-source-iris
configfile: pyproject.toml
testpaths: unit_tests
plugins: anyio-4.15.1, mock-3.15.1
collecting ... collected 72 items

unit_tests/test_db.py::TestFakeSatisfiesProtocol::test_fake_connection_satisfies_dbapi_connection_protocol PASSED [  1%]
unit_tests/test_db.py::TestFakeSatisfiesProtocol::test_fake_cursor_satisfies_dbapi_cursor_protocol PASSED [  2%]
unit_tests/test_db.py::TestConnectRealIris::test_builds_expected_dbapi_connect_kwargs PASSED [  4%]
unit_tests/test_db.py::TestConnectRealIris::test_defaults_port_namespace_and_timeout PASSED [  5%]
unit_tests/test_iris_client.py::TestTestConnection::test_succeeds_against_fake PASSED [  6%]
unit_tests/test_iris_client.py::TestTestConnection::test_raises_on_query_failure PASSED [  8%]
unit_tests/test_iris_client.py::TestListTables::test_excludes_system_schemas_by_default PASSED [  9%]
unit_tests/test_iris_client.py::TestListTables::test_discovers_expected_tables PASSED [ 11%]
unit_tests/test_iris_client.py::TestListTables::test_explicit_schema_filter_bypasses_exclusion_list PASSED [ 12%]
unit_tests/test_iris_client.py::TestListTables::test_columns_populated_with_primary_key_flag PASSED [ 13%]
unit_tests/test_iris_client.py::TestListTables::test_table_without_primary_key PASSED [ 15%]
unit_tests/test_iris_client.py::TestListTables::test_lob_column_flagged PASSED [ 16%]
unit_tests/test_iris_client.py::TestListTables::test_uses_bound_parameters_not_string_interpolation_for_schema_filter PASSED [ 18%]
unit_tests/test_iris_client.py::TestReadFullRefresh::test_reads_all_rows_in_requested_columns PASSED [ 19%]
unit_tests/test_iris_client.py::TestReadFullRefresh::test_respects_requested_column_subset_and_order PASSED [ 20%]
unit_tests/test_iris_client.py::TestReadFullRefresh::test_generated_sql_quotes_identifiers PASSED [ 22%]
unit_tests/test_iris_client.py::TestReadIncremental::test_first_sync_with_no_state_reads_everything_in_cursor_order PASSED [ 23%]
unit_tests/test_iris_client.py::TestReadIncremental::test_resumes_strictly_after_cursor_value PASSED [ 25%]
unit_tests/test_iris_client.py::TestReadIncremental::test_cursor_value_passed_as_bound_parameter PASSED [ 26%]
unit_tests/test_iris_client.py::TestReadIncremental::test_orders_ascending_by_cursor PASSED [ 27%]
unit_tests/test_source_check.py::TestCheckConnection::test_success PASSED [ 29%]
unit_tests/test_source_check.py::TestCheckConnection::test_failure_when_query_fails PASSED [ 30%]
unit_tests/test_source_check.py::TestCheckConnection::test_failure_when_connection_cannot_be_established PASSED [ 31%]
unit_tests/test_source_check.py::TestCheckConnection::test_check_via_airbyte_protocol_message PASSED [ 33%]
unit_tests/test_source_check.py::TestCheckConnection::test_check_failure_via_airbyte_protocol_message PASSED [ 34%]
unit_tests/test_source_discover.py::TestDiscover::test_discover_returns_one_stream_per_table PASSED [ 36%]
unit_tests/test_source_discover.py::TestDiscover::test_table_with_single_column_pk_supports_incremental PASSED [ 37%]
unit_tests/test_source_discover.py::TestDiscover::test_table_without_pk_is_full_refresh_only PASSED [ 38%]
unit_tests/test_source_discover.py::TestDiscover::test_json_schema_reflects_column_types_and_nullability PASSED [ 40%]
unit_tests/test_source_discover.py::TestDiscover::test_namespace_set_to_iris_schema PASSED [ 41%]
unit_tests/test_source_discover.py::TestDiscover::test_tables_config_filter_restricts_discovery PASSED [ 43%]
unit_tests/test_source_discover.py::TestDiscover::test_discover_via_airbyte_entrypoint PASSED [ 44%]
unit_tests/test_source_read.py::TestFullRefreshRead::test_reads_every_row PASSED [ 45%]
unit_tests/test_source_read.py::TestFullRefreshRead::test_full_refresh_via_airbyte_entrypoint PASSED [ 47%]
unit_tests/test_source_read.py::TestIncrementalRead::test_first_sync_emits_all_records_and_final_state PASSED [ 48%]
unit_tests/test_source_read.py::TestIncrementalRead::test_resume_from_state_only_reads_newer_rows PASSED [ 50%]
unit_tests/test_source_read.py::TestIncrementalRead::test_no_new_rows_since_state_emits_zero_records PASSED [ 51%]
unit_tests/test_spec.py::test_spec_loads_via_cdk_base_connector_spec_method PASSED [ 52%]
unit_tests/test_spec.py::test_spec_password_field_is_marked_as_airbyte_secret PASSED [ 54%]
unit_tests/test_spec.py::test_spec_required_fields_present PASSED        [ 55%]
unit_tests/test_spec.py::test_spec_round_trips_through_connector_specification_serializer PASSED [ 56%]
unit_tests/test_spec.py::test_connection_specification_is_a_valid_draft7_json_schema PASSED [ 58%]
unit_tests/test_spec.py::test_valid_config_validates_against_connection_specification PASSED [ 59%]
unit_tests/test_spec.py::test_config_missing_required_field_fails_validation PASSED [ 61%]
unit_tests/test_spec.py::test_spec_via_airbyte_entrypoint_cli PASSED     [ 62%]
unit_tests/test_streams.py::TestStreamIdentity::test_name_is_schema_qualified PASSED [ 63%]
unit_tests/test_streams.py::TestStreamIdentity::test_primary_key_single_column PASSED [ 65%]
unit_tests/test_streams.py::TestStreamIdentity::test_primary_key_none_when_table_has_none PASSED [ 66%]
unit_tests/test_streams.py::TestStreamIdentity::test_supports_incremental_true_when_cursor_field_set PASSED [ 68%]
unit_tests/test_streams.py::TestStreamIdentity::test_supports_incremental_false_without_cursor_field PASSED [ 69%]
unit_tests/test_streams.py::TestStreamFullRefreshRead::test_read_records_full_refresh PASSED [ 70%]
unit_tests/test_streams.py::TestStreamIncrementalRead::test_read_records_incremental_from_scratch PASSED [ 72%]
unit_tests/test_streams.py::TestStreamIncrementalRead::test_state_advances_as_records_are_read PASSED [ 73%]
unit_tests/test_streams.py::TestStreamIncrementalRead::test_read_records_incremental_resumes_from_state PASSED [ 75%]
unit_tests/test_streams.py::TestStreamIncrementalRead::test_state_setter_replaces_state PASSED [ 76%]
unit_tests/test_streams.py::TestStreamIncrementalRead::test_get_json_schema_includes_all_columns PASSED [ 77%]
unit_tests/test_type_mapping.py::TestQuoteIdent::test_wraps_in_double_quotes PASSED [ 79%]
unit_tests/test_type_mapping.py::TestQuoteIdent::test_escapes_embedded_double_quotes PASSED [ 80%]
unit_tests/test_type_mapping.py::TestQuoteIdent::test_none_raises PASSED [ 81%]
unit_tests/test_type_mapping.py::TestQuoteIdent::test_quote_qualified PASSED [ 83%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_bigint_maps_to_integer_with_big_integer_marker PASSED [ 84%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_varchar_maps_to_string PASSED [ 86%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_nullable_column_gets_null_in_type_union PASSED [ 87%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_not_nullable_column_has_scalar_type PASSED [ 88%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_timestamp_maps_to_date_time_string PASSED [ 90%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_date_maps_to_date_string PASSED [ 91%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_high_precision_decimal_marked_big_number PASSED [ 93%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_high_precision_zero_scale_numeric_marked_big_integer PASSED [ 94%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_low_precision_decimal_has_no_airbyte_type_marker PASSED [ 95%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_unknown_type_falls_back_to_string PASSED [ 97%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_lob_types_flagged PASSED [ 98%]
unit_tests/test_type_mapping.py::TestMapIrisType::test_case_insensitive PASSED [100%]

=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
<frozen abc>:106
  ExperimentalClassWarning: This class is experimental. Use at your own risk.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============================= slowest 10 durations =============================
0.01s call     unit_tests/test_source_read.py::TestFullRefreshRead::test_full_refresh_via_airbyte_entrypoint
0.01s call     unit_tests/test_source_read.py::TestIncrementalRead::test_first_sync_emits_all_records_and_final_state
0.01s call     unit_tests/test_source_read.py::TestIncrementalRead::test_resume_from_state_only_reads_newer_rows
0.01s call     unit_tests/test_source_read.py::TestIncrementalRead::test_no_new_rows_since_state_emits_zero_records
0.01s call     unit_tests/test_source_discover.py::TestDiscover::test_discover_via_airbyte_entrypoint

(5 durations < 0.005s hidden.  Use -vv to show these durations.)
======================== 72 passed, 3 warnings in 1.46s ========================
```

This is the complete, unedited output (only the venv's absolute path in the
platform line was shortened to `.../venv/bin/python`). The 3 warnings are
`ExperimentalClassWarning` from `airbyte_cdk` itself, about a class internal to
the CDK, not this connector's code.

This run covers, against `unit_tests/fakes.py::FakeIrisConnection` (never a live
IRIS instance):
- `check` success and 2 distinct failure modes (query failure, connection
  failure) — `test_source_check.py`, plus via the real `AbstractSource.check()`
  protocol object, not just the Python-level `check_connection()` helper.
- `discover` output shape: one stream per table, correct `supported_sync_modes`,
  `default_cursor_field`, `source_defined_primary_key`, JSON Schema per column
  (type + nullability) — `test_source_discover.py`, including one test that runs
  `discover` through the actual `airbyte_cdk.entrypoint.AirbyteEntrypoint` (the
  real CDK CLI dispatcher), not just our own Python API.
- Full-refresh read, both via `AbstractSource.read()` directly and via
  `AirbyteEntrypoint` end to end — `test_source_read.py::TestFullRefreshRead`.
- Incremental read with **state resume**, run three ways: first sync (empty
  state) emitting all rows plus a final `STATE` message with the right cursor
  value; resuming from a saved state and getting only the rows newer than it;
  resuming from a state that is already caught up and getting zero rows —
  `test_source_read.py::TestIncrementalRead`, all through the real
  `AirbyteEntrypoint`, asserting on the actual `STATE`/`RECORD` JSON messages it
  emits.
- `spec.yaml` validated three independent ways: loaded through the CDK's own
  `ConnectorSpecificationSerializer`/`BaseConnector.spec()`; checked as a
  syntactically valid Draft-07 JSON Schema via the `jsonschema` library
  (`jsonschema.Draft7Validator.check_schema`); and round-tripped through the
  real CLI `spec` command via `AirbyteEntrypoint` — `test_spec.py`.
- SQL-injection-shaped safety: a hostile identifier (`Robert"; DROP TABLE
  Patient; --`) round-trips through `quote_ident` without breaking out of its
  quoting; the generated SQL for schema filters and cursor thresholds is
  asserted to use `?` placeholders and never contain the raw value spliced into
  the SQL text — `test_type_mapping.py::TestQuoteIdent`,
  `test_iris_client.py::test_uses_bound_parameters_not_string_interpolation_for_schema_filter`,
  `::test_cursor_value_passed_as_bound_parameter`.
- Type mapping for every case documented in README.md's table, including the
  `airbyte_type: big_integer`/`big_number` precision markers and the
  unknown-type fallback — `test_type_mapping.py`.

### A real bug this test-first process caught and fixed before it shipped

Early full test runs (`unit_tests/test_source_read.py::TestFullRefreshRead::test_reads_every_row`)
**hung indefinitely, consuming multiple GB of RAM**, when reading a
full-refresh-only stream (no cursor field) through the real
`AbstractSource.read()`/`Stream.read()` machinery. Root cause: `IrisTableStream`
mixes in `CheckpointMixin` unconditionally (needed for incremental streams), and
the base `Stream.is_resumable` property infers `True` for *any* class that
defines a `state` property setter — including our full-refresh-only streams,
which have no real cursor. That made the CDK pick a resumable-full-refresh
checkpoint reader that expects `stream_slices()` to eventually signal
completion via changing state; our (default, single, unchanging) slice never
does, so it looped forever re-requesting the same slice. Fixed by overriding
`IrisTableStream.is_resumable` to return `False` whenever no cursor field is
configured (`source_iris/streams.py`) — reproduced the hang, applied the fix,
reran, confirmed 72/72 pass with no hang. This is called out here rather than
silently fixed because it's exactly the kind of thing that would have shipped
undetected without actually running the code through the real CDK entrypoint
end to end.

### Static checks

```
$ python -m py_compile source_iris/*.py unit_tests/*.py && echo "COMPILE OK"
COMPILE OK
$ python -m pyflakes source_iris unit_tests
(no output — clean)
```

### Contribution-layout research is against real, current files, not guesses

Fetched raw file contents directly from `airbytehq/airbyte`'s `master` branch
(via `raw.githubusercontent.com`, since `docs.airbyte.com` and `api.github.com`
are not reachable from this environment's egress proxy — see "UNVERIFIED"):
`source-pokeapi/metadata.yaml`, `.../acceptance-test-config.yml`,
`source-firebolt/{metadata.yaml,pyproject.toml,acceptance-test-config.yml,
source_firebolt/{run.py,source.py,spec.json,database.py,utils.py,__init__.py}}`,
`source-google-sheets/metadata.yaml`, `source-tidb/metadata.yaml`. These are
cited by path throughout `README.md`/`PUBLISHING.md`/source docstrings, and are
the basis for: no-Dockerfile-for-Python-connectors, the `metadata.yaml` shape,
the `pyproject.toml`/poetry shape, `license: ELv2` even for community
connectors, and the `run.py`/`__init__.py` entrypoint pattern.

### IRIS SQL/`INFORMATION_SCHEMA` facts — sourced from InterSystems' own docs via search snippets, not by fetching the full page

`docs.intersystems.com` is blocked by this environment's egress proxy (`curl`
to it returns `connect_rejected` / `CONNECT tunnel failed, response 403`), but
the `WebSearch` tool's underlying fetch is not subject to the same block and
returned real snippets of the actual pages, with real URLs, for:
- `INFORMATION_SCHEMA.COLUMNS` has a `PRIMARY_KEY` column (`YES`/`NO`) and the
  standard `DATA_TYPE`/`IS_NULLABLE`/`CHARACTER_MAXIMUM_LENGTH`/
  `NUMERIC_PRECISION`/`NUMERIC_SCALE` columns.
- `INFORMATION_SCHEMA.TABLES` has `TABLE_SCHEMA`/`TABLE_NAME`/`TABLE_TYPE`.
- `%Library.PosixTime`'s documented ODBC type is `TIMESTAMP`; its logical
  representation is an encoded 64-bit signed integer where the 1970-01-01 epoch
  is `1152921504606846976`, not `0`.
- IRIS stream types (`%Stream.GlobalCharacter`/`%Stream.GlobalBinary`, ODBC
  `LONGVARCHAR`/`LONGVARBINARY`) cannot appear in `WHERE`/predicate or most
  scalar-function contexts (SQLCODE `-313`/`-37`).
- `iris.dbapi.connect`'s documented keyword arguments: `hostname`, `port`,
  `namespace`, `username`, `password`, `timeout`.

These are real citations (URLs in `README.md`/`source_iris/*.py`), but "a search
snippet of the real page" is weaker evidence than "the full page, read end to
end" — treat the exact wording/edge cases (e.g. whether `PRIMARY_KEY` is
case-sensitive `'YES'`, whether there are other `IS_NULLABLE` values) as
snippet-sourced, not page-read-in-full.

## UNVERIFIED (Docker-based acceptance tests and anything needing live IRIS)

- **Nothing in this connector has ever connected to a real IRIS instance.**
  There is no running IRIS and no Docker daemon in this environment. Every
  `check`/`discover`/`read` claim above that isn't explicitly about the
  unreachable-host failure path is about the fake (`FakeIrisConnection`), not a
  real database.
- **The `%PosixTime` ODBC-vs-logical-value question is unresolved.** README.md
  documents the risk directly: if `iris.dbapi`'s cursor returns the *logical*
  (raw encoded 64-bit integer) representation for a `%PosixTime` column instead
  of the documented ODBC display-mode string, this connector will silently pass
  that huge integer through as a "timestamp" string. Nothing here can rule that
  out without a real `%PosixTime` column to query.
- **What the DB-API driver actually returns for a stream/LOB column** (a plain
  string vs. a stream-handle object requiring `.read()`) is unconfirmed for the
  same reason.
- **Docker-based Connector Acceptance Tests (CAT)** — `acceptance-test-config.yml`
  was hand-built to match real connectors' shape (see VERIFIED above) but CAT
  itself was never run; it requires building the connector's Docker image and
  Docker was not available.
- **Airbyte's own QA-check tooling and `airbyte-ci`** were not run (they live
  inside the `airbytehq/airbyte` monorepo's own CI/toolchain, not something this
  session cloned or executed) — see `PUBLISHING.md` for what was and wasn't
  confirmed about the build convention.
- **`docs.airbyte.com` and `api.github.com` are unreachable** from this
  environment's egress proxy (`curl` returns `connect_rejected` /
  "GitHub access to this repository is not enabled for this session" for
  unauthenticated API calls); `raw.githubusercontent.com` and the `WebSearch`
  tool worked and were used instead (see VERIFIED). Anything cited as "per
  Airbyte's docs" is via `WebSearch` snippets or the GitHub MCP `search_code`
  tool, not a direct fetch of the doc page.
- **Views are never discovered** (`TABLE_TYPE = 'BASE TABLE'` only) — a
  deliberate scope cut (see README.md), not something a live instance was used
  to validate either way.
- **User-selectable cursor fields are not implemented** — cursor selection is
  automatic (single-column, non-LOB primary key only). A real user with a table
  whose good cursor candidate isn't its primary key gets full-refresh only.

## HUMAN ACTIONS REQUIRED

1. **Run this against a real IRIS instance** (any edition/version with a
   reachable superserver port) before treating anything beyond the "VERIFIED"
   section above as more than "should work per documentation and offline
   tests." At minimum: `check`, `discover` against a schema with a `%PosixTime`
   column and a stream/LOB column, and a full incremental sync with state
   resume against a table that actually gets new rows between syncs.
2. **Decide who owns the airbytehq/airbyte contribution relationship** and the
   licensing question (contributing means ELv2; this staged copy currently sits
   under whatever license governs `iris-ai-examples`) — see `PUBLISHING.md`
   section 7.
3. **Get a real icon** — `icon.svg` is a generic placeholder, explicitly not
   InterSystems' trademarked logo; brand/marketing sign-off is needed before
   contributing upstream.
4. **Re-resolve the `connectorBuildOptions.baseImage` digest** in `metadata.yaml`
   at actual contribution time — the one there was copied from another
   connector's metadata.yaml fetched during this build and will be stale by
   then.
5. **Provision real test secrets** in Airbyte's GSM-backed testing secret store
   (`SECRET_SOURCE-IRIS_CREDS`, referenced in `metadata.yaml`) if/when this is
   actually contributed — nothing here has real credentials or a real target.

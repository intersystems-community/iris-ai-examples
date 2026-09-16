# Status

## VERIFIED

Claims below are backed by pasted, real command output or a directly
fetched primary source in this session.

- **ADF has no generic JDBC linked service; ODBC is the only user-driver
  path.** Verified by grepping the vendored, real Azure ARM schema for
  `Microsoft.DataFactory` (fetched from
  `https://raw.githubusercontent.com/Azure/azure-resource-manager-schemas/master/schemas/2018-06-01/Microsoft.DataFactory.json`,
  HTTP 200, 1,187,618 bytes, saved at `vendor/Microsoft.DataFactory.2018-06-01.json`):

  ```
  $ python3 -c "
  import json
  d = json.load(open('vendor/Microsoft.DataFactory.2018-06-01.json'))
  print([k for k in d['definitions'] if 'Odbc' in k or 'Jdbc' in k])
  "
  ['OdbcLinkedServiceTypeProperties', 'OdbcTableDatasetTypeProperties']
  ```

- **The ODBC connector requires a self-hosted integration runtime; Azure
  IR is not an option.** Fetched directly (not search-summarized) from
  `https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/data-factory/connector-odbc.md`
  (HTTP 200), which states Copy activity and Lookup activity both support
  self-hosted IR only, and "A 64-bit ODBC driver is required."

- **Fabric Data Factory's ODBC connector uses a different gateway product
  (the on-premises data gateway) and a different resource model
  (Connections, not ARM linked services) than classic ADF.** Fetched
  directly from `MicrosoftDocs/fabric-docs` (all HTTP 200):
  `docs/data-factory/connector-odbc.md`,
  `docs/data-factory/connector-odbc-copy-activity.md`,
  `docs/data-factory/how-to-access-on-premises-data.md` — the last one
  states "You need an on-premises data gateway version 3000.214.2 or
  later to support Fabric pipelines," the same gateway product used by
  Power BI/Power Automate, not the ADF self-hosted IR binary.

- **Generated ARM JSON validates against the real Microsoft.DataFactory
  ARM schema.** `schemas/adf-schema-subset.json` is a trimmed, byte-for-byte
  copy of definitions from the vendored schema above (built by
  `schemas/build_schema_subset.py`, not hand-transcribed), including the
  `expression` pattern resolved from the real
  `arm-common-definitions.json` (also vendored). 64 pytest tests validate
  every generated linked service / dataset / pipeline / copy-activity
  source-sink / integration-runtime resource against it with real
  `jsonschema` Draft-04 validation, and separately assert the validator
  rejects a bogus connector type and a resource name containing a literal
  `/` (the exact schema-invalidating bug found and fixed during this
  session — see `_factory_resource`'s docstring in
  `generator/generate_adf_templates.py`). Full pytest run, clean venv:

  ```
  $ python3 -m venv /tmp/adf_iris_venv
  $ /tmp/adf_iris_venv/bin/pip install -r requirements.txt
  Successfully installed attrs-26.1.0 iniconfig-2.3.0 jsonschema-4.26.0 \
    jsonschema-specifications-2025.9.1 packaging-26.3 pluggy-1.6.0 \
    pygments-2.21.0 pytest-9.1.1 referencing-0.37.0 rpds-py-2026.6.3 \
    typing-extensions-4.16.0

  $ /tmp/adf_iris_venv/bin/python -m pytest tests/ -v
  ============================= test session starts ==============================
  ...
  64 passed in 0.12s
  ```

- **Connection-string construction is correct across ten parameter
  permutations** (default/custom port, multiple namespaces, IP vs. FQDN
  host, alternate driver names, extra ODBC keywords, and a value
  containing `;`/`=` that must be `{brace}`-quoted or it corrupts the
  string) — `tests/test_connection_strings.py`, all passing in the run
  above.

- **Secrets are never inlined.** `IrisConnectionConfig` has no `password`
  field (`TypeError` if you try); the generated `password` field is always
  `{"type": "AzureKeyVaultSecret", ...}`, never `SecureString`; the same
  policy is enforced for the sink storage connection string;
  `tests/test_secrets.py` (8 tests) all pass in the run above.

- **The IRIS ODBC read-failure symptom "connects, lists tables, fails to
  read rows" is a real, reported issue, not invented for this task.**
  Found via web search pointing at
  `https://community.intersystems.com/post/issue-accesing-cach%C3%A9-database-tables-azure-datafactory`,
  with the error text `ERROR [HY000] [Cache ODBC][State : S1000][Native
  Code 400] [SQLCODE: <-400>]` and `%All`-role permission as the reported
  fix, corroborated by a second thread
  (`community.intersystems.com/post/cache-odbcstate-s1000native-code-400`)
  discussing the same SQLCODE -400 as a generic fatal-error code that
  masks the real underlying cause (permissions or data-type conversion).

## UNVERIFIED

Everything below needs a live IRIS instance, a live Azure Data Factory,
or both — neither exists in this session (no Azure subscription, no
running IRIS container, no Docker daemon; see `../../CLAUDE.md`).

- **Nothing has been deployed.** No template in `templates/`, and no
  output of `generator/generate_adf_templates.py`, has ever been submitted
  to `az deployment group validate` or `az deployment group create`, let
  alone actually run a Copy activity against a real IRIS table. All
  "validation" performed is offline `jsonschema` conformance against
  Microsoft's ARM schema definitions, not an ARM `whatIf`/`validate` call
  against a live subscription (Azure access does not exist in this
  session), and not a real Copy activity run.

- **The exact wording of the InterSystems ODBC connection-parameters and
  intro docs** (`docs.intersystems.com`) — this session's egress proxy
  blocked direct `WebFetch` to `docs.intersystems.com` on every attempt.
  The connection-string keyword names (`Driver`, `Server`, `Port`,
  `Database`, `UID`, `PWD`) and the two observed driver-name variants
  (`InterSystems ODBC`, `InterSystems IRIS ODBC35`) come from a search
  engine's indexed summary of that page, not a page fetch this session
  performed itself. Treat the keyword names as reliable (they match the
  well-known InterSystems ODBC connection-string grammar used elsewhere)
  but the exact document wording as unconfirmed.

- **Which root cause — missing `%All`/resource privilege, or a date/time
  type-conversion failure — actually explains the `-400` symptom** in any
  given deployment. Both are documented in different community threads
  for the same error code; this session could not fetch either thread's
  full text directly (`community.intersystems.com` was also blocked by
  the egress proxy on every attempt), only search-engine summaries of
  them, and had no live IRIS+ADF pair to reproduce and discriminate
  between the two. `README.md` states this plainly rather than picking
  one.

- **The separate `HYC00`/native code `469` "no rows returned" symptom**
  reported against some ODBC client tools but not others (Excel/SSIS
  reportedly fine, a replication tool reportedly not) — no root cause or
  fix was found in the sources available to this session. Stated as
  unresolved in `README.md`, not guessed at.

- **Whether the InterSystems ODBC driver is available/certified for a
  Linux self-hosted IR host**, vs. requiring the Windows-only classic
  self-hosted IR. `README.md`'s setup steps flag this as something to
  confirm against current Microsoft SHIR OS-support docs and current
  InterSystems driver downloads for your specific IRIS version, rather
  than asserting an answer this session could not check end-to-end.

- **Whether `az deployment group create` accepts these exact templates
  without modification** (parameter-file wiring, resource-group/location
  specifics, an actual existing Data Factory to target) — no Azure CLI
  with real credentials was available to run this.

- **A Fabric-native generator target** (Fabric Connections REST API /
  Git-integration item format instead of ARM `linkedservices`) does not
  exist in this directory. `README.md`'s Fabric section explains why the
  ARM templates don't carry over and what would need to be built instead;
  nothing here builds it.

## HUMAN ACTIONS REQUIRED

- Get access to a real Azure subscription and a real IRIS/Caché instance
  (or `careconnect-sdoh`'s IRIS container, pointed at from a network the
  self-hosted IR can reach) to actually run `az deployment group create`
  against these templates and a Copy activity against real data. Nothing
  in this session can do that.
- On the actual self-hosted IR host you'll use, run `odbcinst -q -d`
  (Linux) or open the ODBC Data Source Administrator (Windows) and
  confirm the registered InterSystems ODBC driver name before setting
  `IrisConnectionConfig.driver_name` / the `odbcDriverName` template
  parameter — do not trust the `InterSystems ODBC35` default blindly.
- If you hit the `-400` "connects, lists tables, fails on read" symptom:
  check the connecting IRIS user's SQL privileges (or grant `%All`, if
  that's an acceptable scope for a read-only ETL account, which it
  usually isn't for anything beyond a quick isolation test) first, then
  check whether the query touches date/time columns, before assuming
  either cause. Report back which one it actually was — this repo
  couldn't establish that, and a confirmed answer would improve
  `README.md` for the next person.
- Read `docs.intersystems.com`'s ODBC pages directly (this session's
  network could not) and confirm the exact connection-string grammar and
  current driver-name conventions for the IRIS version you're targeting.
- Grant the target Data Factory's managed identity `Get` permission on
  secrets in the Key Vault referenced by these templates — no template
  here does this for you; it's a Key Vault access-policy or RBAC change
  against a real Key Vault this session cannot make.
- If a native connector is the actual goal rather than the generic-ODBC
  workaround this directory provides: read `PUBLISHING.md` and start the
  Microsoft partner-engineering conversation it describes. That is a
  business-development action, not something achievable by writing more
  code here.

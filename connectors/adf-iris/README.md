# Azure Data Factory <-> InterSystems IRIS

## Scope, stated honestly, first

**Azure Data Factory (ADF) has no public SDK or partner program for
third-party linked-service connectors.** Unlike Snowflake or Databricks
(which Microsoft ships as first-class, named ADF connectors with their own
docs pages, IntelliSense, and testing UI), there is no mechanism by which
InterSystems, or anyone outside Microsoft, can add a native "IRIS" entry to
the ADF linked-service picker. This directory does **not** attempt to build
one, because that isn't buildable from the outside. See `PUBLISHING.md` for
what actually getting a native entry would require.

What *is* buildable, and what this directory delivers:

1. A researched, cited answer to "does ODBC or JDBC actually work for IRIS
   in ADF today, and under what integration runtime" (below).
2. Parameterized ARM JSON templates for the linked service, dataset, and
   copy activity that make the generic ODBC path reproducible instead of
   something every team reverse-engineers from scratch.
3. A Python generator that produces those same ARM payloads from a
   connection config and a table list, so a 40-table migration doesn't mean
   hand-editing 40 near-identical JSON files (and the password never has a
   chance to end up pasted into one of them).
4. Tests that validate the generated JSON against Microsoft's own ARM
   schema for `Microsoft.DataFactory`, not a hand-rolled approximation of
   it.

**Nothing here has been deployed against a real Data Factory or a real IRIS
instance.** There is no Azure subscription, no running IRIS container, and
no Docker daemon available in this environment (see `../../CLAUDE.md` and
`STATUS.md`). Every claim below is either backed by a cited primary source
or a pasted command, or is explicitly marked as unverified.

## ODBC vs. JDBC: which one actually works

**ODBC is the connector. There is no generic JDBC linked service in ADF.**

This is not "ODBC is preferred" — it's that ADF's ARM resource model does
not have a JDBC option at all for user-supplied drivers. Confirmed directly
against the schema Azure itself publishes and that `az` and the ARM
deployment engine validate against:

```
$ python3 -c "
import json
d = json.load(open('vendor/Microsoft.DataFactory.2018-06-01.json'))
matches = [k for k in d['definitions'] if 'Odbc' in k or 'Jdbc' in k]
print(matches)
"
['OdbcLinkedServiceTypeProperties', 'OdbcTableDatasetTypeProperties']
```
(schema fetched from
<https://raw.githubusercontent.com/Azure/azure-resource-manager-schemas/master/schemas/2018-06-01/Microsoft.DataFactory.json>,
the same store VS Code's ARM tooling and `az deployment` validate against —
see `vendor/` for the vendored copy and provenance.)

Named connectors that happen to use JDBC under the hood (Hive, Spark,
Presto, Impala, Google BigQuery's older path) are each their own
Microsoft-shipped linked-service type with a bundled driver. There is no
`"type": "Jdbc"` a third party can point at an arbitrary driver JAR the way
`"type": "Odbc"` lets you point at an arbitrary ODBC driver. This matches
what [Microsoft Q&A and the ADF docs corpus](https://learn.microsoft.com/en-us/answers/questions/88256/jdbc-query-as-source-in-azure-data-factory-pipelin)
say when people ask for one: use ODBC.

The [ODBC connector docs](https://learn.microsoft.com/en-us/azure/data-factory/connector-odbc)
state the IR requirement plainly:

| Supported capability | Integration runtime |
| --- | --- |
| Copy activity (source/sink) | Self-hosted only |
| Lookup activity | Self-hosted only |

> "A 64-bit ODBC driver is required."

**Azure IR cannot be used.** There is no way to reach an on-prem or
private-network IRIS instance from the Azure-managed IR without a
self-hosted IR in between, and even if IRIS were reachable, Azure IR has no
mechanism to install a third-party ODBC driver on it. Every template in
this directory assumes a self-hosted IR (see
`templates/self-hosted-integration-runtime.json`).

### The InterSystems ODBC driver and connection string

Per the InterSystems ODBC driver docs
(<https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=BNETODBC_parms>,
<https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=BNETODBC_intro>
— both blocked from direct fetch by this session's egress proxy; the
connection-string keywords below come from that page's indexed search
summary, not a verbatim page read, so treat the *keyword names* as
verified and the *exact wording of the docs* as unverified, see
`STATUS.md`):

```
Driver=InterSystems ODBC Driver;Server=127.0.0.1;Port=1972;Database=USER;UID=myUsername;PWD=
```

Keywords: `Driver`, `Server` (host), `Port` (superserver port, 1972
default), `Database` (the IRIS **namespace**, e.g. `USER`), `UID`, `PWD`.
The default InterSystems username is `_SYSTEM`. On the self-hosted IR host
the driver is registered under a name that varies by platform/version —
seen in the docs as both `InterSystems ODBC` and `InterSystems IRIS
ODBC35` — so **verify it on your actual IR host** with:

```
odbcinst -q -d          # Linux/unixODBC: lists registered driver names
```

or the ODBC Data Source Administrator on Windows, before deploying any
template here. `generator/generate_adf_templates.py`'s
`IrisConnectionConfig.driver_name` takes this as a required-by-convention
parameter rather than hardcoding a default that's wrong for half of
installs.

### The known failure mode: connects, lists tables, fails to read rows

Reported directly by an ADF + Caché/IRIS user (InterSystems Developer
Community,
<https://community.intersystems.com/post/issue-accesing-cach%C3%A9-database-tables-azure-datafactory>):
the ODBC linked service connects, the table picker in ADF Studio lists
Caché/IRIS tables, and the Copy activity then fails while reading rows with
an error resembling:

```
ERROR [HY000] [Cache ODBC][State : S1000][Native Code 400] [SQLCODE: <-400>]
```

**What -400 means, per InterSystems' own SQLCODE reference:** `-400` is a
generic "fatal error occurred" code, used when a more specific SQLCODE
isn't available — i.e. the error text itself doesn't pin down the cause;
you have to look at what's underneath it.

**Two documented causes for this specific symptom, from search-indexed
community threads (not independently reproduced here — no live IRIS or ADF
in this environment):**

1. **Missing privilege on the resource behind the table.** The community
   thread's own stated fix: grant the connecting user the `%All` role (or,
   more narrowly, the SQL privilege on the specific database resource the
   table lives in — checkable via System Administration > Configuration >
   System Configuration > Local Databases in the Management Portal). A user
   that can list tables via ODBC metadata calls but lacks `SELECT`
   privilege reads as "connects fine, fails on the actual query."
2. **A data type ADF's ODBC driver can't convert**, most often a
   date/time column whose on-the-wire representation doesn't match what
   the generic ODBC path expects. Other -400 threads in the same community
   trace to this instead of permissions.

**We could not establish from available evidence which of these is the
cause in any given case** — the two root causes look identical from the
error code alone, and this session has no live IRIS + ADF pairing to
reproduce either one and confirm. If you hit this: check the connecting
user's privileges first (cheap to rule out), then check whether the query
selects any date/time/timestamp columns and try excluding them one at a
time. Do not treat either explanation as confirmed without testing against
your own instance.

A second, separate report exists for a **"no rows returned"** symptom with
error `[Cache ODBC][State : HYC00][Native Code 469]`, reported as
working from Excel/SSIS but failing from certain other ODBC client tools.
No root cause or fix was established in the sources available to this
session — **stated plainly as unresolved**, not guessed at.

## Does this carry over to Fabric Data Factory?

**Partially, and not at the ARM-template level.** Fabric Data Factory does
have an ODBC connector
(<https://raw.githubusercontent.com/MicrosoftDocs/fabric-docs/main/docs/data-factory/connector-odbc.md>,
`connector-odbc-copy-activity.md`), and its Copy-activity JSON vocabulary
is recognizably the same shape: `source.type` includes an ODBC source with
`query`/`tableName`, `queryTimeout`, and it's Basic/Anonymous-auth like
classic ADF. But two things are genuinely different, not just renamed:

1. **No `Microsoft.DataFactory/factories/linkedservices` ARM resource in
   Fabric.** Fabric replaces the linked-service-in-ARM model with a
   centrally managed **Connection** object (created via the Fabric portal
   or Fabric REST API / Git integration), which a pipeline activity
   references by connection ID. None of the ARM templates in `templates/`
   deploy as-is against a Fabric workspace — there's no ARM endpoint for
   Fabric items in the first place.
2. **The gateway is a different product.** Fabric's docs are explicit:
   on-prem access requires the **on-premises data gateway** (the same
   gateway product used by Power BI and Power Automate,
   "version 3000.214.2 or later" per
   <https://raw.githubusercontent.com/MicrosoftDocs/fabric-docs/main/docs/data-factory/how-to-access-on-premises-data.md>),
   **not** the classic ADF self-hosted integration runtime binary. You
   install a different agent even though both ultimately just host ODBC
   drivers on a box you control.

What *would* carry over directly: the connection-string construction logic
(`generator.build_connection_string`) and the copy-activity source/sink
vocabulary (`OdbcSource`/query, `tableName`). A Fabric-targeting generator
would reuse those and swap the ARM linked-service/dataset builders for
calls against the Fabric Connections REST API — not built here; flagged as
the natural next increment in `STATUS.md`.

## What's in this directory

```
templates/    Hand-authored, parameterized ARM templates -- one per
               resource -- meant to be deployed with
               `az deployment group create --template-file ... --parameters ...`
               against an EXISTING factory (they use the
               "[concat(parameters('factoryName'), '/', name)]" ARM idiom).
generator/     generate_adf_templates.py -- the testable core. Builds the
               same resource shapes programmatically from an
               IrisConnectionConfig + a table list, nested under a new
               factory resource. Use this when you have more than a
               couple of tables, or want the same environment's config
               reproduced without hand-editing JSON.
schemas/       adf-schema-subset.json: a trimmed, verbatim (not
               hand-retyped) subset of Microsoft's real ARM schema for
               Microsoft.DataFactory, used by the tests. build_schema_subset.py
               regenerates it from vendor/.
vendor/        The full, unmodified schema files fetched from
               Azure/azure-resource-manager-schemas, for provenance.
tests/         pytest suite -- see below.
PUBLISHING.md  What a native ADF/Fabric IRIS connector would actually take.
STATUS.md      VERIFIED / UNVERIFIED / HUMAN ACTIONS REQUIRED.
```

## Using the generator

```python
from generator import IrisConnectionConfig, generate_bundle

config = IrisConnectionConfig(
    host="iris-prod.internal",
    username="adf_reader",
    key_vault_secret_name="iris-adf-reader-pwd",   # the password itself is
                                                     # never a parameter here
    namespace="SQLUser",
)

bundle = generate_bundle(
    config,
    tables=["SQLUser.Patient", "SQLUser.Encounter"],
    factory_name="adf-iris-prod",
    key_vault_base_url="https://kv-iris-prod.vault.azure.net/",
    storage_container="iris-export",
    storage_connection_string_secret_name="blob-conn-string",
)

# bundle["template"] is one deployable ARM template with the self-hosted
# IR, the Key Vault / IRIS / Blob linked services, and one dataset pair +
# copy pipeline per table.
import json
print(json.dumps(bundle["template"], indent=2))
```

Save that to a file and deploy with:

```
az deployment group create --resource-group <rg> --template-file bundle.json
```

## Running the tests

```
pip install -r requirements.txt
python -m pytest tests/ -v
```

64 tests, all passing offline (no network, no Azure, no IRIS) — pasted
output in `STATUS.md`. They check three things:

1. **Real schema conformance.** Every linked service, dataset, pipeline,
   copy-activity source/sink, and integration-runtime resource the
   generator (and the static templates in `templates/`) produce is
   validated with `jsonschema` Draft-04 against `schemas/adf-schema-subset.json`
   — a trimmed but byte-for-byte copy of Microsoft's own schema, not an
   approximation. `test_schema_validation.py` also asserts the validator
   *rejects* a bogus linked-service type and a resource name containing a
   literal `/` (the exact bug this generator had mid-development — see the
   docstring on `_factory_resource`), so a schema that silently accepted
   everything wouldn't pass this suite unnoticed.
2. **Connection-string correctness** across ten parameter permutations
   (custom port, namespace, driver name, extra ODBC keywords, values
   needing `{brace}` quoting), plus a round-trip parser.
3. **Secrets policy.** The password field is always an
   `AzureKeyVaultSecret` reference, never `SecureString`/plaintext; the sink
   storage connection string follows the same rule; `IrisConnectionConfig`
   doesn't even accept a `password=` kwarg (`TypeError`, not a silent
   no-op); and a set of plaintext markers are asserted absent from the
   serialized template.

## Setting up the self-hosted IR host

1. Install the self-hosted IR agent (Windows) per
   <https://learn.microsoft.com/en-us/azure/data-factory/create-self-hosted-integration-runtime>.
2. Install the InterSystems ODBC driver for that platform, from the IRIS
   distribution or InterSystems' driver downloads. Confirm the registered
   driver name with `odbcinst -q -d` (Linux self-hosted IR is supported by
   ADF's SHIR for Linux; verify current OS support in Microsoft's SHIR
   docs before relying on it) or the ODBC Data Source Administrator
   (Windows) — do not assume `InterSystems ODBC35` is correct for your
   install.
3. Confirm the self-hosted IR host can reach the IRIS superserver port
   (1972 by default) over the network — this is a different port from the
   management/web port (52773).
4. Deploy `templates/self-hosted-integration-runtime.json`, register the
   agent with the key ADF gives you, then deploy the remaining templates
   in dependency order: Key Vault linked service -> IRIS ODBC linked
   service -> Blob linked service -> datasets -> pipeline.
5. Grant the Data Factory's managed identity `Get` on secrets in the
   target Key Vault's access policy (or an equivalent RBAC role
   assignment) — the templates reference Key Vault secrets by name, but
   nothing in ARM grants that access automatically.

None of steps 1-5 have been executed in this session (no Azure
subscription, no IRIS container, no self-hosted IR host available) — see
`STATUS.md`.

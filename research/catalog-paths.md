# Catalog Paths — what it takes to get IRIS listed

Execution plan for every catalog in [`ecosystem-connector-gaps.md`](ecosystem-connector-gaps.md):
for each one, the development projects, the non-engineering tasks, the shared
foundations it depends on, and what "listed" means. Implementations referenced here
live in [`../connectors/`](../connectors/).

> Generated from the same data as the published artifact *Where IRIS Isn't Listed*,
> so the two agree. Edit both together.

## Where things stand

| Status | Catalogs | Meaning |
| --- | --- | --- |
| **Built — validate & submit** (6) | #1, #2, #5, #7, #9, #10 | Implementation exists; the host has an open submission route. |
| **Built — listing gated** (4) | #3, #4, #6, #8 | Implementation exists; the branded listing needs the host vendor to act. |
| **Not started — buildable** (8) | #11, #12, #13, #15, #17, #18, #21, #23 | No implementation yet; the host has a route InterSystems can use unilaterally. |
| **Partnership only** (3) | #14, #19, #20 | No route InterSystems can take alone; the host vendor must build or list it. |
| **Waiting on the host** (1) | #16 | The host's catalog cannot list IRIS yet, however good the integration. |
| **Not pursued** (1) | #22 | The host is architecturally closed to IRIS; revisit only if a foundation changes that. |

**The single critical path:** every one of the ten built connectors is blocked on **F1**, a
live IRIS instance to validate against. Nothing else resolves their open questions, and no
submission should go out before it.

Sizes are rough single-engineer estimates: **S** ≈ days · **M** ≈ 1–3 weeks · **L** ≈ a month or more.

## What this round changed

- **Fabric has a real listing — and it is cheap.** Microsoft maintains an Open Mirroring Partner Ecosystem page with a named entry per partner; Informatica, MongoDB, Qlik Replicate and CData are on it. That is a branded listing for #5 that needs no Microsoft engineering, which the Fabric connector's PUBLISHING.md had omitted (now added). Effort stays at 2, and the payoff rises.
- **Airflow's registry can't list IRIS yet.** The registry lists only official Apache providers; third-party support is planned, not live. #16 is waiting on the host, not on IRIS.
- **Zapier doesn't fit self-hosted IRIS.** Zapier requires a publicly launched product with a public HTTPS API, then 10 templates and 50 active users. Only a hosted InterSystems cloud service qualifies.
- **Five connectors duplicate the same risky code.** MCP, Fivetran, Airbyte, Fabric and the OData producer each reimplement `INFORMATION_SCHEMA` discovery on the same unverified assumptions. A shared library (F11) turns five validations into one.
- **Carried forward from the implementation round.** Salesforce effort 5 → 3 via the OData connector; Fivetran's Partner-Built program is closed; ADF is ODBC-only; submit AI Hub's MCP server rather than the reference one.

## Shared foundations

Workstreams that several catalog paths depend on. Each path below cites them by ID
instead of repeating them.

| ID | Foundation | Kind | Size | Owner | Unblocks |
| --- | --- | --- | --- | --- | --- |
| **F1** | Live IRIS validation environment | Development | M | Data Platform engineering + Developer Relations | 18: #1, #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #17, #18, #20, #21, #23 |
| **F2** | Connector homes and CI | Development | M | Developer Relations (placement decision: engineering leadership) | 4: #1, #4, #9, #18 |
| **F3** | Publisher identity and accounts | Task | S | Alliances + IT/Security | 11: #1, #2, #4, #5, #6, #7, #10, #11, #13, #15, #18 |
| **F4** | Brand assets and sign-off | Task | S | Marketing / brand | 4: #1, #7, #9, #15 |
| **F5** | Legal: licences, signing, privacy | Task | S | Legal + Security | 6: #2, #7, #9, #16, #17, #18 |
| **F6** | Primary-doc re-verification | Task | S | Each connector's owner | 5: #3, #5, #7, #8, #10 |
| **F7** | Community reconciliation | Task | S | Developer Relations | 5: #1, #10, #12, #16, #17 |
| **F8** | Security review | Task | M | Security | 5: #1, #2, #6, #10, #21 |
| **F9** | Productize iris-pgwire | Development | L | Data Platform product management + engineering | 4: #3, #14, #19, #22 |
| **F10** | Content and search | Task | S | Product marketing | 3: #3, #4, #8 |
| **F11** | Shared IRIS catalog and type-mapping library | Development | M | Data Platform engineering | 6: #4, #5, #6, #9, #11, #23 |

### F1 — Live IRIS validation environment

*Development · M · Data Platform engineering + Developer Relations*

A shared IRIS every connector's integration suite runs against: IRIS Community in CI (docker-compose or Testcontainers) plus one persistent, network-reachable instance that vendor sandboxes — Databricks, Snowflake, Fabric, Data 360, an Azure self-hosted IR — can connect to. Seed it with a fixture schema covering every awkward case the connectors flagged: `%PosixTime`, `%Stream`, NUMERIC precision and scale, `%Boolean`, vectors, composite and missing primary keys.

**Why it matters:** Every built connector is blocked on this and nothing else resolves its open questions: `INFORMATION_SCHEMA` column names, Grafana's REST/SQL response shape, Tableau's window functions and DATEADD date parts, Kafka's `INSERT OR UPDATE`, Fivetran's `%Boolean` and PosixTime handling, and ADF's -400 error.

### F2 — Connector homes and CI

*Development · M · Developer Relations (placement decision: engineering leadership)*

Decide where each connector lives and extract it from `iris-ai-examples/connectors/` with history. Some hosts dictate the answer: Airbyte into the `airbytehq/airbyte` monorepo, Fivetran into `fivetran/community_connectors`, Grafana, Tableau and Terraform into a public repo the publisher owns. Each repo gets CI running tests, lint, build and the F1 integration suite.

**Why it matters:** Grafana and Terraform submissions require a stable public GitHub URL, and `iris-ai-examples` is scoped to AI demos, not production connectors.

### F3 — Publisher identity and accounts

*Task · S · Alliances + IT/Security*

InterSystems-owned accounts — never personal ones — on every host: a grafana.com org with an Access Policy Token; Fivetran; Tableau Technology Partner; Confluent's partner portal; Salesforce Partner Community plus a Data 360 sandbox; a Fabric tenant with a service principal; an Azure subscription; the MCP registry namespace (GitHub org or DNS TXT for `com.intersystems`); a Claude.ai org with Directory permission; an OpenAI developer org with Apps Management: Write; an AWS Marketplace seller account.

**Why it matters:** Reviewers weigh whether a submission reads as the vendor or as an individual — Fivetran's community repo has a single maintainer, and Grafana reviews manually.

### F4 — Brand assets and sign-off

*Task · S · Marketing / brand*

An approved IRIS logo and icon in each host's required formats, with trademark-usage sign-off, replacing the placeholders now in Grafana (`src/img/logo.svg`), Airbyte (`icon.svg`), Tableau and the MCP manifest. Plus screenshots and a short demo per connector, captured against F1.

**Why it matters:** Grafana's catalog requires screenshots, and none of the placeholder logos may ship.

### F5 — Legal: licences, signing, privacy

*Task · S · Legal + Security*

Per-repo licence decisions — contributing to Airbyte means ELv2; Superset and Airflow need ASF contributor licence agreements; Atlan's SDK is Apache 2.0. A code-signing certificate for the Tableau `.taco`, a GPG key for Terraform releases, and a public privacy-policy URL, which Claude's directory, desktop extensions and ChatGPT all require.

**Why it matters:** Each is a hard gate at submission time and slow to obtain, so start early.

### F6 — Primary-doc re-verification

*Task · S · Each connector's owner*

Re-read every vendor-spec claim marked search-derived in a connector's STATUS.md against the primary page, from an unrestricted network. The build environment could not reach docs.databricks.com, docs.snowflake.com, learn.microsoft.com, docs.confluent.io, docs.airbyte.com, grafana.com or docs.intersystems.com.

**Why it matters:** Cheap, and a precondition for trusting any DDL grammar or submission checklist in these repos.

### F7 — Community reconciliation

*Task · S · Developer Relations*

Agree supersede, merge or co-maintain with the authors of existing community work before submitting anything that overlaps it: caretdev's `grafana-intersystems-datasource`, `mcp-server-iris`, `dbt-iris`, `superset-iris`, `sqlalchemy-iris`, `n8n-nodes-iris` and `airflow-provider-iris`, and the author of `confluent-kafka-iris`.

**Why it matters:** A near-duplicate by another author is a predictable rejection risk in Grafana's manual review — and these maintainers carry most of the community's goodwill.

### F8 — Security review

*Task · M · Security*

Review and threat-model everything that executes caller-supplied SQL or holds credentials: the MCP read-only guard, OData `$filter` translation, the Kafka sink, the Grafana backend, and any hosted endpoint.

**Why it matters:** The Kafka connector has had no security review at all, and two connectors translate untrusted input into SQL.

### F9 — Productize iris-pgwire

*Development · L · Data Platform product management + engineering*

Take `iris-pgwire` from community project to supported feature: native TLS (it currently recommends an nginx or HAProxy front end), pooling, auth, and a compatibility matrix against the PostgreSQL connectors of Databricks federation, Snowflake Snowpark, Hightouch, Census, Sigma, Omni and Looker.

**Why it matters:** The only foundation that opens catalogs on its own — connect as Postgres — though it never earns a branded IRIS tile.

### F10 — Content and search

*Task · S · Product marketing*

InterSystems-owned pages for IRIS + Snowflake, IRIS + Databricks and IRIS + Fabric making the federate-don't-copy argument, plus a launch post per connector on the Developer Community.

**Why it matters:** Reclaims search results currently owned by Matillion's and CData's IRIS pages. No engineering; can start today.

### F11 — Shared IRIS catalog and type-mapping library

*Development · M · Data Platform engineering*

Five Python connectors — MCP, Fivetran, Airbyte, Fabric and the Salesforce OData producer — each reimplement `INFORMATION_SCHEMA` discovery, and three carry separate IRIS type maps, all resting on the same unverified assumptions. Extract one library, validate it once against F1, and make each connector depend on it.

**Why it matters:** Turns five separate live-IRIS validations into one, and gives the next Python connectors (Atlan, Meltano, dlt) validated code to start from.

## Sequencing

0. **Start now, in parallel.** Foundations with long lead times and no dependencies. — F1 live IRIS environment; F3 accounts; F4 brand; F5 legal; F7 community reconciliation; F10 content; Placement decision for F2.
1. **Publish what exists.** Validated against F1, then submitted. No new engineering beyond fixes. — #1 Grafana; #2 AI directories via AI Hub; #12 dbt Trusted; #17 Superset.
2. **Validated submissions.** Built connectors needing live-tenant or live-worker proof first. — #4 Fivetran community; #5 Fabric Open Mirroring partner listing; #7 Tableau; #9 Airbyte; #10 Confluent Hub.
3. **Partnership motions.** Open these early — lead times are months — and feed them proofs from the previous phases. — #3 Databricks and Snowflake; #5 native Fabric source; #6 Salesforce; #8 ADF native; #13 AWS; #14 Looker; #19 Hightouch.
4. **New builds.** Start once F1 and F11 exist, so each begins from validated code. — #11 Atlan and Alation; #13 Athena; #21 Trino; #18 Terraform; #15 Zapier, if a hosted service is chosen.

## Path per catalog

### #1 Grafana plugin catalog

**Status:** Built — validate & submit · **Tier** 1 · **Owner:** Developer Relations, with Data Platform engineering on D1

**What exists:** `connectors/grafana-iris-datasource` — Go backend over the Atelier REST/SQL API plus SAM metrics, TypeScript config and query editors. `go test` and Jest pass; cross-compiles for Linux, macOS and Windows.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Validate and fix REST/SQL response parsing in `rest_client.go` against live IRIS | S | The top risk: the parsed shape came from forum posts, and the offline test server encodes the same assumption, so the current tests cannot catch it being wrong. |
| D2 | End-to-end tests against a live Grafana + IRIS stack | M | Drive the config editor, query editor and a dashboard panel; reuse the existing `docker-compose.yaml` and provisioning. |
| D3 | Build hygiene: triage the 8 `npm audit` findings, run eslint and prettier | S | All in devDependencies, but they block a clean CI. |

**Tasks**

- *Decide* — Community or Commercial signature level — a business decision about the Grafana relationship that changes what can be submitted.
- *Coordinate* — Settle the relationship with `caretdev/grafana-intersystems-datasource` — supersede, merge or differentiate — before submitting (F7).
- *Accounts* — grafana.com org and Access Policy Token for signing (F3).
- *Legal & brand* — Replace the placeholder logo; capture screenshots and a demo against live IRIS for the catalog listing (F4).
- *Submit* — Sign the plugin and submit it for catalog review.

**Depends on:** F1, F2, F3, F4, F7, F8

**Listed when:** Signed plugin listed in the Grafana catalog and installable with `grafana cli plugins install`.

### #2 AI agent connector directories

**Status:** Built — validate & submit · **Tier** 1 · **Owner:** AI Hub product team

**What exists:** `connectors/mcp-iris` — a reference stdio MCP server (96 tests, ~50 of them SQL-guard bypass attempts), a `server.json` validated against the MCP registry schema, and a desktop-extension manifest validated with the official `mcpb` CLI.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Confirm AI Hub's `iris-mcp-server` speaks Streamable HTTP, and add it if not | M | Claude's Connectors Directory no longer accepts SSE, and ChatGPT needs a public HTTP(S) endpoint. |
| D2 | Hosted public HTTPS endpoint with OAuth for the directory listing | M | Both directories gate on a reachable, domain-verified deployment. |
| D3 | Port the reference server's adversarial SQL-guard tests to the AI Hub server | S | Only if AI Hub lacks equivalent coverage; the ~50 bypass cases are reusable as-is. |

**Tasks**

- *Decide* — Submit AI Hub's `iris-mcp-server`, not the reference server — it is HTTP-capable and has an owner who can pass domain verification.
- *Decide* — Choose `packages` or `remotes` distribution for the `server.json` entry.
- *Validate* — Confirm `catalog.py`'s `INFORMATION_SCHEMA` names against a live namespace if the reference server stays in use (F1).
- *Accounts* — MCP registry namespace via GitHub org or DNS TXT; Claude.ai org with Directory permission; OpenAI developer org with Apps Management: Write (F3).
- *Legal & brand* — Publish a privacy-policy URL — every one of these directories rejects submissions without one (F5).
- *Submit* — MCP registry publish, Claude Connectors Directory, desktop extension, then ChatGPT's portal. ChatGPT has no public manifest schema; it is portal submission plus domain verification only.

**Depends on:** F1, F3, F5, F8

**Listed when:** `com.intersystems` listed in the MCP registry, and IRIS present in the Claude Connectors Directory and ChatGPT's app directory.

### #3 Snowflake and Databricks source lists

**Status:** Built — listing gated · **Tier** 1 · **Owner:** Alliances (lead) + Solutions Engineering

**What exists:** `connectors/databricks-snowflake-federation` — Unity Catalog bring-your-own-driver JDBC DDL and a partitioned Spark read for Databricks; External Access Integration plus Snowpark DB-API over `iris-pgwire` for Snowflake. 57 tests on the builders.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Databricks proof of concept: DDL runs, `PushedFilters` shows in `.explain()`, partitioned reads work | M | Needs a real workspace and the IRIS JDBC JAR on a Unity Catalog volume. |
| D2 | Snowflake proof of concept: `session.read.dbapi` loads rows through `iris-pgwire` | M | Depends on a supported, TLS-terminated pgwire deployment (F9). |
| D3 | Evaluate `iris-pgwire` through Databricks' native PostgreSQL federation connector | M | Higher upside than D1: IRIS arrives through an already-named connector. |

**Tasks**

- *Validate* — Re-verify the DDL grammar against primary Databricks and Snowflake docs before running anything (F6).
- *Partnership* — Find a joint healthcare customer running IRIS alongside Databricks or Snowflake.
- *Partnership* — Package the proven recipe as a co-branded reference architecture with that customer.
- *Partnership* — Route it through Alliances to each vendor's partner engineering team. Their pattern for documenting a non-native source is almost always 'a customer asked and we wrote it up', not an unsolicited docs PR.
- *Content* — IRIS + Databricks and IRIS + Snowflake pages making the federate-don't-copy case (F10).

**Depends on:** F1, F6, F9, F10

**Listed when:** IRIS named in a Databricks or Snowflake doc, solution page or reference architecture.

### #4 Fivetran

**Status:** Built — listing gated · **Tier** 1 · **Owner:** Alliances + Developer Relations

**What exists:** `connectors/fivetran-iris` — Connector SDK source, 75 tests. `fivetran debug` was run for real and caught a genuine bug (Fivetran's `UTC_DATETIME` parser rejects IRIS PosixTime strings), now fixed.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Live-IRIS validation across the fixture schema | S | `%PosixTime`, `%Stream`, NUMERIC precision and scale, no-PK and composite-PK tables, and `%Boolean` — the last two assumptions were already patched once after running real code. |
| D2 | Conform to the `fivetran/community_connectors` layout, with CI running pytest and `fivetran debug` | S | `fivetran debug` needs no credentials, so it belongs in CI. |
| D3 | Migrate catalog discovery and type mapping onto the shared library | S | Once F11 exists. |

**Tasks**

- *Accounts* — An InterSystems-owned Fivetran account, so the pull request reads as the vendor (F3).
- *Submit* — Self-serve `fivetran deploy` for customers who need it now.
- *Submit* — Pull request to `fivetran/community_connectors` for visibility.
- *Partnership* — Alliances asks Fivetran about an exception to the Partner-Built program, which is closed to new partners — it is the only route to a branded catalog tile.
- *Content* — Launch post once the pull request merges (F10).

**Depends on:** F1, F2, F3, F10, F11

**Listed when:** Merged into `fivetran/community_connectors`. A branded catalog tile additionally needs Fivetran to reopen Partner-Built.

### #5 Microsoft Fabric mirroring

**Status:** Built — validate & submit · **Tier** 1 · **Owner:** Data Platform product management + Alliances (Microsoft)

**What exists:** `connectors/fabric-open-mirroring-iris` — Open Mirroring landing-zone writer and crash-safe publisher, 47 tests including a simulated-crash re-run.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | OneLake upload transport | M | ADLS Gen2 / Blob API to `onelake.blob.fabric.microsoft.com` with service-principal auth. The connector builds the correct local tree but never uploads it. |
| D2 | Change-tracking strategy | S–L | S for a watermark and soft-delete convention helper; L for IRIS-journal CDC, the only way to capture hard deletes without an application convention. |
| D3 | Run it as a service | M | Scheduling, configuration, logging, retry and alerting around the publisher. |
| D4 | Confirm the type map against live IRIS and `_partnerEvents.json` placement against a live tenant | S | Both flagged ambiguous in STATUS.md. |

**Tasks**

- *Validate* — End to end in a real tenant: create an open mirrored database, upload, and confirm the mirrored tables in the portal.
- *Accounts* — Fabric tenant and service principal (F3).
- *Partnership* — Get an entry on Microsoft's Open Mirroring Partner Ecosystem page — a named listing that needs no Microsoft engineering, only Microsoft's partner team (the page lists named reviewers). Informatica, MongoDB, Qlik Replicate and CData are already there.
- *Partnership* — In parallel, the joint-engineering ask for native mirrored-source status, citing the certified Power BI connector as precedent.

**Depends on:** F1, F3, F6, F11

**Listed when:** InterSystems listed on the Open Mirroring Partner Ecosystem page. Native mirrored-source status is the longer, separate goal.

### #6 Salesforce Data Cloud (Data 360)

**Status:** Built — listing gated · **Tier** 1 · **Owner:** Alliances (Healthcare & Life Sciences partnerships)

**What exists:** `connectors/salesforce-zero-copy-iris` — a stdlib-only OData v4 producer over IRIS SQL for Data 360's OData connector, which Salesforce documents as beta for Zero Copy query federation. 58 tests including injection cases.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | HTTP layer with auth | M | WSGI/ASGI, or an IRIS-native CSP REST handler; the producer currently has no server around it. |
| D2 | Validate against a Data 360 org | M | OData version, capability annotations, pagination and auth as the connector actually expects them. |
| D3 | Live-IRIS validation, then migrate `schema.py` onto the shared library | S | F1, then F11. |

**Tasks**

- *Decide* — Pursue named Zero Copy Partner Network membership, or ship the OData path quietly — it delivers the capability with no permission needed, but no co-marketing.
- *Validate* — Confirm the beta terms with Salesforce's connector team — beta features can change or be withdrawn before anyone represents this as durable.
- *Accounts* — Salesforce Partner Program enrolment and a Data 360 sandbox org (F3).
- *Partnership* — Ask Salesforce directly whether the Zero Copy Partner Network takes new members, using a joint Health Cloud customer as the lever.

**Depends on:** F1, F3, F8, F11

**Listed when:** Capability: Data 360 federating IRIS through the OData connector in a real org. Listing: named in the Zero Copy Partner Network.

### #7 Tableau Exchange

**Status:** Built — validate & submit · **Tier** 2 · **Owner:** Product management, BI connectivity — the Power BI connector's owners

**What exists:** `connectors/tableau-iris` — full Connector SDK source tree, every packaged file validated against Tableau's real XSDs, 47 tests.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Settle the dialect's open questions against live IRIS | S | DATEADD, DATEDIFF and DATEPART date-part spellings; whether DATENAME and DATETRUNC exist; and window functions, where IRIS docs and `sqlalchemy-iris`'s tests disagree. |
| D2 | Run TDVT and fix what it finds | L | Needs Windows, Tableau Desktop and live IRIS loaded with the TDVT dataset. TDVT typically surfaces many dialect fixes. |
| D3 | Package and sign with `connector-packager` | S | Needs the signing certificate (F5). |

**Tasks**

- *Decide* — Fix the `class='iris_jdbc'` value deliberately — Tableau never allows it to change after acceptance.
- *Validate* — Re-read the gallery-submission and package-signing docs directly (F6).
- *Accounts* — Tableau Technology Partner enrolment (F3).
- *Legal & brand* — Code-signing certificate (F5); connector icon (F4).
- *Submit* — Tableau Exchange submission.

**Depends on:** F1, F3, F4, F5, F6

**Listed when:** Signed `.taco` listed on Tableau Exchange.

### #8 Azure Data Factory

**Status:** Built — listing gated · **Tier** 2 · **Owner:** Solutions Engineering + Alliances (Microsoft)

**What exists:** `connectors/adf-iris` — parameterized ARM templates and a generator, validated against Microsoft's real ARM schema, 64 tests. ADF has no JDBC linked-service type, so ODBC on a self-hosted integration runtime is the only route.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Deploy to a real subscription and run a Copy activity against live IRIS | M | Through a self-hosted integration runtime. |
| D2 | Diagnose the -400 error and document the cause | S | Connects and lists tables, then fails reading rows — SQL privileges or a date/time conversion, still undetermined. |
| D3 | Fabric Data Factory equivalent | M | The ARM templates do not carry over: Fabric uses a different gateway and a Connections resource model. |

**Tasks**

- *Validate* — Confirm the registered ODBC driver name on the integration-runtime host (`odbcinst -q -d`) rather than trusting the default.
- *Validate* — Re-read InterSystems' ODBC connection-string docs directly (F6).
- *Partnership* — Microsoft partner-engineering ask for a native linked service — bundle it with the Fabric mirroring ask.
- *Content* — Publish the validated recipe, including the -400 answer (F10).

**Depends on:** F1, F6, F10

**Listed when:** Recipe validated and published now. A native connector in ADF's list is Microsoft-built.

### #9 Airbyte

**Status:** Built — validate & submit · **Tier** 2 · **Owner:** Developer Relations

**What exists:** `connectors/airbyte-source-iris` — CDK source with full contribution scaffolding, 72 tests. Test-first caught a stream that hung with multi-gigabyte memory growth.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Live-IRIS validation | S | `check`, `discover` against `%PosixTime` and stream columns, and an incremental sync that resumes across new rows. |
| D2 | Run Airbyte's Docker-based acceptance tests | M | Could not run without a Docker daemon. |
| D3 | Refresh the `metadata.yaml` base-image digest at contribution time | S | The current one was copied from another connector and will be stale. |

**Tasks**

- *Decide* — Name the owner of the `airbytehq/airbyte` contribution relationship.
- *Legal & brand* — Accept ELv2 for the contributed code (F5); supply a real icon (F4).
- *Submit* — Pull request to `airbytehq/airbyte` at community tier; Airbyte provisions the test secrets in its own store. Certified tier later.

**Depends on:** F1, F2, F4, F5, F11

**Listed when:** `source-iris` in Airbyte's connector registry — which also carries it into Estuary, which relists Airbyte connectors.

### #10 Confluent Hub

**Status:** Built — validate & submit · **Tier** 2 · **Owner:** Interoperability product management

**What exists:** `connectors/kafka-connect-iris` — source and sink, real Maven build, 57 tests against H2 as a stand-in for IRIS.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Replace H2 with IRIS in the test suite | M | Especially `UPSERT_NATIVE` (IRIS's `INSERT OR UPDATE`), which has zero coverage because H2 does not implement it. |
| D2 | End to end on a real Connect worker and topic | S | Standalone mode is enough. |
| D3 | Build the Confluent Hub component archive | S | `manifest.json`, `lib/`, `etc/`, `doc/`, `assets/`, validated with a real `confluent-hub-client install`. |

**Tasks**

- *Decide* — Name the owner among Alliances, Interoperability PM and Developer Relations.
- *Validate* — Re-read Confluent's component-archive spec and Verified Integration Program pages (F6).
- *Coordinate* — Reconcile with `confluent-kafka-iris` on Open Exchange — duplicate, supersede or merge (F7).
- *Partnership* — Apply to Confluent's Verified Integration Program.

**Depends on:** F1, F3, F6, F7, F8

**Listed when:** Listed on Confluent Hub; Verified tier as a follow-on.

### #11 Atlan, Collibra and Alation

**Status:** Not started — buildable · **Tier** 2 · **Owner:** Product management (data governance) + Alliances

**What exists:** Nothing yet. The three differ: Collibra accepts your own JDBC driver with no build; Atlan and Alation need a connector built on their SDKs.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Atlan metadata connector on the Application SDK | M | Python, Apache 2.0; custom connectors publish into Atlan exactly like native ones. |
| D2 | Alation connector on the Open Connector Framework | M | Alation runs an OCF partner program alongside the SDK. |

**Tasks**

- *Validate* — Collibra: register IRIS with its own JDBC driver through Edge, then document the working recipe.
- *Partnership* — Enrol in Alation's OCF partner program; open an Atlan partner conversation.

**Depends on:** F1, F3, F11

**Listed when:** IRIS listed in the Atlan and Alation connector galleries, with a documented Collibra recipe.

### #12 dbt Trusted Adapter Program

**Status:** Not started — buildable · **Tier** 2 · **Owner:** Developer Relations

**What exists:** `dbt-iris`, a community adapter maintained by caretdev — outside this repo.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Gap assessment against dbt's essential functionality and the adapter test suite | S | Trusted status requires covering dbt v1's essentials, with best effort on the rest. |
| D2 | Close the gaps found | M | Incremental strategies and snapshots are the usual shortfalls. |
| D3 | Setup and configuration pages on docs.getdbt.com | S | dbt's docs site must be the single source of truth for the adapter. |

**Tasks**

- *Decide* — Commit to an ongoing maintenance cadence — keeping pace with dbt releases is a condition of Trusted status, not a one-time bar.
- *Coordinate* — Agree adoption or co-maintenance with the `dbt-iris` maintainer (F7).
- *Submit* — Apply to the Trusted Adapter Program.

**Depends on:** F1, F7

**Listed when:** `dbt-iris` listed as a Trusted adapter on docs.getdbt.com.

### #13 AWS Glue, DMS and Athena

**Status:** Not started — buildable · **Tier** 2 · **Owner:** Alliances (AWS)

**What exists:** Nothing yet. The three services differ: Athena and Glue have self-serve routes, DMS does not.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Athena connector on the Query Federation SDK | M | Java on Lambda — one function for metadata, one for records. Anyone can self-publish to the Serverless Application Repository. |
| D2 | Glue: a tested custom JDBC connection recipe | S | Uses the IRIS JDBC driver; a Glue Marketplace connector is a larger follow-on. |

**Tasks**

- *Accounts* — AWS Marketplace seller account and APN engagement (F3).
- *Partnership* — DMS source endpoints are AWS-built — a partnership ask only.
- *Partnership* — Ask for Athena's official listing: the 'Amazon Athena Federation' author name is reserved for AWS-built connectors.

**Depends on:** F1, F3

**Listed when:** Athena connector in the Serverless Application Repository under InterSystems, then an official AWS listing.

### #14 Looker dialects

**Status:** Partnership only · **Tier** 2 · **Owner:** Alliances (Google Cloud)

**What exists:** Nothing. Looker has no partner dialect SDK; Google implements dialects, and requests go through a Looker or Google contact.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Test `iris-pgwire` under Looker's PostgreSQL dialect | S | A stopgap only, and it depends on F9. |

**Tasks**

- *Partnership* — Ask Google for IRIS at Looker's 'Integration' support level — the lighter tier, with no ongoing test commitment from Google, and so the more realistic first ask.
- *Content* — Gather customer demand evidence; demand is what Looker weighs when adding dialects.

**Depends on:** F9

**Listed when:** IRIS listed among Looker's dialects, at Integration level or above.

### #15 Zapier, Make and Workato

**Status:** Not started — buildable · **Tier** 3 · **Owner:** Cloud services product management

**What exists:** Nothing. Zapier requires a publicly launched product with a public HTTPS API and public API docs, then 10 published templates and 50 active users. A self-hosted database meets none of that, so only a hosted InterSystems cloud service fits.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Zapier integration via the Platform CLI, against a hosted InterSystems service's REST API | M | Make and Workato custom apps follow the same pattern. |

**Tasks**

- *Decide* — Which hosted InterSystems service is the target — without one, there is nothing to integrate.
- *Submit* — Publish 10 Zap templates, then reach 50 active users to launch publicly.

**Depends on:** F3, F4

**Listed when:** Public Zapier app live. This is a search-visibility play, not a data-platform one.

### #16 Airflow Registry

**Status:** Waiting on the host · **Tier** 3 · **Owner:** Developer Relations

**What exists:** `airflow-provider-iris`, community-built and flagged 'Issue Detected' on Open Exchange. The registry lists only official Apache providers; third-party listing is planned but not available.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Clear the Open Exchange flag and harden the provider | S | Worth doing regardless of the registry. |
| D2 | Meet Airflow's acceptance criteria for an official provider | M | Only if InterSystems chooses to donate it to the ASF. |

**Tasks**

- *Decide* — Wait for third-party listing, or donate an official `apache-airflow-providers-*` package with an ongoing maintenance commitment.
- *Coordinate* — With the provider's author (F7).
- *Legal & brand* — ASF contributor licence agreement, if donating (F5).

**Depends on:** F5, F7

**Listed when:** Listed in the Airflow Registry — when the registry supports third-party providers, or on donation.

### #17 Apache Superset docs

**Status:** Not started — buildable · **Tier** 3 · **Owner:** Developer Relations

**What exists:** `superset-iris` and `sqlalchemy-iris` work today; IRIS is absent only from Superset's own database list.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Upstream an IRIS engine spec to `superset/db_engine_specs/` | S | Its `metadata` attribute auto-generates the docs entry, so the code change and the listing are the same pull request. Add time grains and IRIS SQL quirks. |

**Tasks**

- *Coordinate* — With the `superset-iris` author, whose engine-spec work is the natural starting point (F7).
- *Legal & brand* — ASF contributor licence agreement (F5).
- *Submit* — Pull request to `apache/superset`.

**Depends on:** F1, F5, F7

**Listed when:** IRIS appears on Superset's 'Connecting to Databases' page.

### #18 Terraform Registry

**Status:** Not started — buildable · **Tier** 3 · **Owner:** Cloud and DevOps product management

**What exists:** Nothing.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | `terraform-provider-iris` on the plugin framework | L | Resources for namespaces, databases, users, roles and web applications through IRIS's management API. |
| D2 | Release pipeline | S | GoReleaser producing signed SHA256SUMS and semver-tagged GitHub releases. |

**Tasks**

- *Decide* — Whether a provider adds enough over the InterSystems Kubernetes Operator to justify an L-sized build.
- *Accounts* — A public GitHub repo named `terraform-provider-iris` under an InterSystems org (F3).
- *Legal & brand* — An RSA or DSA GPG signing key (F5).

**Depends on:** F1, F2, F3, F5

**Listed when:** Published in the Terraform Registry.

### #19 Hightouch and Census

**Status:** Partnership only · **Tier** 3 · **Owner:** Alliances

**What exists:** Nothing. No self-serve route for adding a source was found; Census is now part of Fivetran.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Test `iris-pgwire` as a PostgreSQL source in both | S | Depends on F9. |

**Tasks**

- *Partnership* — Source request to Hightouch; fold the Census request into the Fivetran conversation.

**Depends on:** F9

**Listed when:** IRIS as a named source in either tool.

### #20 Healthcare real-world-data delivery targets

**Status:** Partnership only · **Tier** 3 · **Owner:** Alliances (Healthcare & Life Sciences)

**What exists:** Nothing. Datavant, Truveta and HealthVerity deliver natively into Snowflake and Databricks.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Delivery-target adapter, once a vendor specifies what it needs | ? | Unscopable until a vendor names its delivery format. |

**Tasks**

- *Partnership* — Joint-customer-led conversations with each vendor, alongside Datavant's existing Databricks Marketplace presence.

**Depends on:** F1

**Listed when:** IRIS named as a delivery destination by at least one vendor.

### #21 Trino and Starburst

**Status:** Not started — buildable · **Tier** 3 · **Owner:** Developer Relations

**What exists:** Nothing. Third-party JDBC plugins built outside the Trino repo are an established pattern — IBM's `trino-db2` is one.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | `trino-iris` plugin on `trino-base-jdbc` | M | Java; reuse the IRIS SQL dialect knowledge from the Kafka connector and Tableau dialect. |
| D2 | Upstream contribution to `trinodb/trino` | L | A high bar and long review; optional. |

**Tasks**

- *Partnership* — Starburst partner listing once the plugin is stable.

**Depends on:** F1, F8

**Listed when:** Plugin published and documented; upstream acceptance optional.

### #22 Sigma, Omni, ThoughtSpot and Hex

**Status:** Not pursued · **Tier** 3 · **Owner:** —

**What exists:** These are warehouse-native by design and will not add IRIS.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | Compatibility test of `iris-pgwire` against the tools that accept PostgreSQL | S | Sigma and Omni both do. Revisit only once F9 ships. |

**Depends on:** F9

**Listed when:** Not a goal. At most, a documented pgwire recipe.

### #23 Long tail

**Status:** Not started — buildable · **Tier** 3 · **Owner:** Developer Relations

**What exists:** Cube, Feast, Monte Carlo, dlt, Meltano, Estuary, Retool — nothing listed anywhere.

**Development projects**

| ID | Project | Size | Notes |
| --- | --- | --- | --- |
| D1 | dlt: documented `sqlalchemy-iris` source | S | dlt's SQL source already takes SQLAlchemy dialects. |
| D2 | Meltano Hub entry | S | Via a Singer tap, or by pointing at the Airbyte connector. |
| D3 | Cube driver and Feast offline store | M | Each; defer until demand appears. |

**Tasks**

- *Partnership* — Monte Carlo is partnership-only.
- *Content* — Estuary comes free once Airbyte lands, since it relists Airbyte connectors.

**Depends on:** F1, F11

**Listed when:** Individually per tool.

## Already covered — no path needed

- **Microsoft Power BI** (Listed) — Certified connector, ships in Power BI Desktop. The model for everything here.
- **Datadog** (Listed) — First-party `intersystems-iris` integration with dashboards and monitors.
- **Matillion** (Listed) — IRIS connector exists — marketed as “InterSystems IRIS to Databricks.”
- **DBeaver** (Listed) — Officially supported; driver fetched on first connect.
- **JetBrains DataGrip** (Listed) — In the databases-with-basic-support list.
- **Metabase** (Community only) — Community driver, listed in Metabase's community-drivers doc.
- **n8n** (Community only) — Community node covering query and insert.
- **KNIME** (Community only) — Works over JDBC, community-documented.


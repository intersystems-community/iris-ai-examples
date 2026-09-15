# Where Snowflake and Databricks Are a Data Source and InterSystems IRIS Is Not

**Ranked by traffic reach × marketing impact for InterSystems**

Research date: 2026-09-15 · Status: desk research, public sources only

---

## Headline finding

**The gap is almost never connectivity. It is catalog presence.**

IRIS ships ODBC, JDBC, DB-API, a SQLAlchemy dialect, and (via `iris-pgwire`) a
PostgreSQL wire-protocol front end. Technically, IRIS can be reached from nearly
every platform on this list. But in ~20 of the highest-traffic integration catalogs
on the internet, a buyer searching for "InterSystems IRIS" finds nothing — while
Snowflake and Databricks have a branded tile, a docs page, a logo, and a
co-marketing launch blog.

Three consequences fall out of that:

1. **Discovery loss.** Integration catalogs are how data teams shortlist platforms
   in 2026. "Is it in Fivetran?" is a procurement question, not a technical one.
2. **SEO surrender.** Third parties already rank for the combination. Matillion
   publishes a live landing page titled *"InterSystems IRIS to Databricks — Connect
   & Load Data in Minutes."* CData sells the same route. Every one of those pages
   frames IRIS as the legacy source you migrate *off*, and InterSystems owns none
   of that search real estate.
3. **Invisible community labor.** Much of the work is already done — by volunteers,
   outside the host catalogs, where it generates zero marketing value. One
   maintainer (caretdev / Dmitry Maslennikov) is behind `sqlalchemy-iris`,
   `superset-iris`, `dbt-iris`, `grafana-intersystems-datasource`,
   `mcp-server-iris`, and `n8n-nodes-iris`. Several of those carry "Issue Detected"
   or "Awaiting Review" status on Open Exchange. That is single-maintainer risk on
   the entire ecosystem surface.

The cheapest wins on this list are not engineering projects. They are **publishing
projects**: take code that exists, harden it, and get it into the host's catalog
under the InterSystems name.

---

## Scoring method

Each platform is scored 1–5 on two axes, then ranked by `Traffic + Impact`, with
effort shown separately as an ROI signal.

| Axis | What it measures |
| --- | --- |
| **Traffic (T)** | Reach of the specific catalog/docs surface where an IRIS tile would appear — installed base, catalog pageview potential, SEO indexation |
| **Impact (M)** | Strategic value to InterSystems: overlap with the IRIS ICP (healthcare providers/payers, financial services, OEM/embedded), competitive displacement value, availability of partner co-marketing, influence on the CDO/CIO buying committee |
| **Effort (E)** | 1 = publish existing code · 3 = build a connector against a documented partner SDK · 5 = requires the other vendor to build it |

**Caveat on traffic:** I could not obtain Similarweb-grade pageview data for these
catalogs. The T column is a modeled estimate anchored on vendor-published scale
figures (cited inline below) plus catalog size and SEO indexation. Validate T with
real analytics before it goes in a partnership deck. The gap/no-gap findings
themselves are sourced and are the durable part of this document.

---

## The ranking

### Tier 1 — Do these first

| # | Platform | Gap | T | M | E | Total |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Grafana plugin catalog** | No IRIS data source in the official catalog | 5 | 4 | **1** | 9 |
| 2 | **AI agent connector directories** (ChatGPT, Claude, MCP registries) | IRIS MCP server exists but is in no directory | 5 | 5 | **1–2** | 10 |
| 3 | **Snowflake & Databricks' own source lists** (Lakehouse Federation, Lakeflow Connect, Openflow) | IRIS absent; Oracle, Teradata, SQL Server, Postgres present | 5 | 5 | 5 | 10 |
| 4 | **Fivetran** | No connector; Fivetran Support confirmed no plans (Jan 2026) | 4 | 5 | 3 | 9 |
| 5 | **Microsoft Fabric mirroring** | Snowflake, Azure Databricks, Oracle (preview) supported; IRIS absent | 4 | 5 | 4 | 9 |
| 6 | **Salesforce Data Cloud Zero Copy Partner Network** | Snowflake, Databricks, BigQuery, Redshift, Microsoft; IRIS absent | 3 | 5 | 5 | 8 |

### Tier 2 — Strong second wave

| # | Platform | Gap | T | M | E | Total |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | **Tableau Exchange / native connector list** | ODBC/JDBC only — no Exchange listing (asymmetric with Power BI, which is done) | 4 | 4 | 2 | 8 |
| 8 | **Azure Data Factory / Fabric Data Factory** | No IRIS linked service; not on the on-prem gateway supported list | 4 | 4 | 4 | 8 |
| 9 | **Airbyte** | "Community Opportunity" only | 4 | 3 | 2 | 7 |
| 10 | **Confluent Hub** | No IRIS connector; community Kafka adapters only | 3 | 4 | 3 | 7 |
| 11 | **Enterprise data catalogs** (Atlan, Collibra, Alation) | No native IRIS connector on any of the three | 3 | 4 | 3 | 7 |
| 12 | **dbt Trusted Adapter Program** | `dbt-iris` exists but is community-tier, not Trusted | 4 | 3 | **1** | 7 |
| 13 | **AWS Glue / DMS / Athena federated query** | Generic JDBC only; IRIS not a named endpoint | 4 | 3 | 4 | 7 |
| 14 | **Looker dialects** | No IRIS dialect (Google must implement) | 4 | 3 | 5 | 7 |

### Tier 3 — Cheap SEO plays and long tail

| # | Platform | Gap | T | M | E | Total |
| --- | --- | --- | --- | --- | --- | --- |
| 15 | **Zapier / Make / Workato** | No IRIS app (n8n has a community node) | 5 | 2 | 2 | 7 |
| 16 | **Airflow Registry** | `airflow-provider-iris` exists off-registry, flagged "Issue Detected" | 3 | 2 | **1** | 5 |
| 17 | **Apache Superset docs** | `superset-iris` works but IRIS is not in Superset's own DB list | 3 | 2 | **1** | 5 |
| 18 | **Terraform Registry** | No IRIS/IKO provider | 3 | 2 | 2 | 5 |
| 19 | **Hightouch / Census** (now Fivetran) | No IRIS source | 2 | 3 | 3 | 5 |
| 20 | **Trino / Starburst** | No IRIS connector | 2 | 2 | 4 | 4 |
| 21 | **Healthcare RWD delivery targets** (Datavant, Truveta, HealthVerity) | Snowflake/Databricks are native delivery destinations; IRIS is not | 2 | 4 | 5 | 6 |
| 22 | **Warehouse-native BI** (Sigma, Omni, ThoughtSpot, Hex) | Architecturally warehouse-only — will not support IRIS | 2 | 1 | 5 | 3 |
| 23 | **Long tail** (Cube, AtScale, Feast, Monte Carlo, Soda, dlt, Meltano, Estuary, Retool) | No IRIS listing anywhere | 1–2 | 1–2 | 2–3 | ≤4 |

---

## Detail on the top six

### 1. Grafana — highest ROI on the entire list

Grafana Labs reports **35M+ users, 10,000+ customers, and $600M+ ARR** (Aug 2026),
and its plugin catalog is a one-click install surface with heavy organic traffic.
Snowflake and Databricks both have signed data source plugins there.

A working IRIS plugin **already exists**: `caretdev/grafana-intersystems-datasource`,
written in Go, using the xDBC protocol, and already able to stream SAM metrics in
real time with history, logs, and alerts. It has never been published to the
Grafana catalog.

This is the clearest case on the list: the code is written, the surface is enormous,
and the remaining work is signing, review, and a listing. It also lands directly on
top of IRIS's own observability story (SAM), so it is a product win as well as a
marketing one.

**Action:** fund the plugin to signed-and-published state under the InterSystems
publisher account. Weeks, not quarters.

### 2. AI agent connector directories — the fastest-moving surface in 2026

Both competitors have first-party managed MCP servers: Snowflake's managed MCP
server (Cortex Agents) and Databricks' MCP support under Unity AI Gateway. OpenAI's
ChatGPT Work Data Agent explicitly names **BigQuery, Snowflake, and Databricks** as
supported sources. Databricks has a connector in the Claude marketplace.

IRIS is *not* technically behind here — AI Hub ships an `iris-mcp-server` MCP
gateway in IRIS 2026.x, and `caretdev/mcp-server-iris` predates it. The gap is
purely **directory presence**: IRIS appears in none of the agent connector
directories, and third parties (CData, BlazeSQL) are the ones listed there, brokering
access to Snowflake and Databricks.

This is the single best place for InterSystems to look *ahead* of the competition
rather than behind it, and given that the server exists, the cost is registry
submissions and a launch post.

**Action:** submit the AI Hub MCP server to the MCP registry, the Claude connector
directory, and ChatGPT's connector directory. Highest urgency because these
directories are being populated right now and early entries compound.

### 3. Snowflake's and Databricks' own source lists — the narrative prize

Databricks Lakehouse Federation supports MySQL, PostgreSQL, Redshift, Snowflake,
SQL Server, Azure Synapse, BigQuery, Teradata, and Databricks-to-Databricks.
Lakeflow Connect covers MySQL, PostgreSQL, Oracle, SQL Server, Salesforce, Workday,
Kafka, and more. IRIS is on neither list.

The subtext matters more than the connector: **Snowflake and Databricks consider
Oracle, Teradata, and SQL Server worth naming as systems of record, and do not
consider IRIS worth naming.** For a platform sold as the system of record for the
world's health data, that omission is the competitive story.

Effort is a 5 because the other vendor has to build it, and neither has an incentive
to. But there is a documented back door on both: Databricks supports "bring your own
driver" JDBC Unity Catalog connections, and both platforms accept community/custom
connectors. A published, documented, InterSystems-supported recipe — plus pressure
via joint customers — gets IRIS named in their docs, which is the most valuable
backlink and credibility asset available.

**Action:** treat this as a partnership/field motion, not an engineering one. Target
getting IRIS named in a Databricks custom-connector or JDBC-federation doc via a
joint healthcare customer.

### 4. Fivetran — the confirmed, on-the-record "no"

Fivetran serves roughly **6,300 customers** with 700+ connectors, and its connector
catalog is one of the most heavily indexed integration surfaces on the web. Its
acquisition of Census folded reverse ETL into the same ecosystem, so one absence now
costs InterSystems presence in two categories.

This is the best-documented gap of the set: Fivetran Support stated in January 2026
that there are **no confirmed plans** for an InterSystems IRIS connector, and the
InterSystems Ideas portal request (DPI-I-449) has been downgraded to "Community
Opportunity" — i.e. InterSystems is not building it either. Both sides have formally
declined.

Fivetran does run a partner-built connector program with a public Connector SDK, so
InterSystems can build and own this without waiting for Fivetran's roadmap.

**Action:** build against the Fivetran Connector SDK and pursue partner-built
certification. This is the flagship "IRIS is a first-class citizen of the modern data
stack" proof point.

### 5. Microsoft Fabric mirroring — where IRIS's install base is going

Fabric mirroring supports Azure SQL, SQL Managed Instance, Cosmos DB, Azure
Databricks, PostgreSQL, Snowflake, SQL Server, and Oracle (preview). IRIS is absent.

This ranks high on impact rather than raw traffic because of ICP fit: a very large
share of IRIS's provider install base is a Microsoft shop whose analytics roadmap now
runs through Fabric and OneLake. Snowflake being a mirrorable source while IRIS is
not means that in every one of those accounts, the path of least resistance is to copy
clinical data out of IRIS into a mirrored competitor. Oracle reaching preview status
shows Microsoft will onboard non-Microsoft OLTP sources when the partner pushes.

**Action:** joint engineering ask into the Fabric mirroring team, with the Power BI
certified connector as the precedent and relationship.

### 6. Salesforce Data Cloud Zero Copy Partner Network — best co-marketing value

Launch partners were AWS/Redshift, Databricks, Google BigQuery, and Snowflake, later
joined by Microsoft. Snowflake and BigQuery are GA; Databricks and Redshift followed.

Traffic is a 3 — this is a partner program, not a high-pageview catalog — but impact
is a 5 for two reasons. First, adjacency: Salesforce Health Cloud sits in exactly the
provider and payer accounts where IRIS is the system of record, and zero-copy is
precisely the "don't move the clinical data" argument InterSystems already makes.
Second, this program comes with the most generous co-marketing machinery of anything
on the list — press release inclusion, Dreamforce presence, a partner directory tile.

**Action:** partnership-led. Lowest technical lift-to-visibility ratio if InterSystems
can get admitted.

---

## Where IRIS is already fine — do not spend here

Several ecosystems that look like gaps are already closed. Listing them so effort
isn't duplicated:

| Platform | Status |
| --- | --- |
| **Microsoft Power BI** | ✅ Certified connector, ships in Power BI Desktop (now "InterSystems Health Insight Connector"). The model for everything else on this list. |
| **Datadog** | ✅ First-party `intersystems-iris` integration in integrations-core, with dashboards and monitors. Recently landed. |
| **Matillion** | ✅ IRIS connector exists — and Matillion markets "InterSystems IRIS **to Databricks**". Covered, but see the SEO problem below. |
| **DBeaver** | ✅ Officially supported (driver downloaded on first connect). |
| **JetBrains DataGrip** | ✅ Listed under databases with basic support. |
| **dbt** | ⚠️ `dbt-iris` community adapter works; gap is Trusted Adapter tier only. |
| **Metabase** | ⚠️ Community driver exists and IRIS is listed in Metabase's community-drivers doc. |
| **Apache Superset** | ⚠️ `superset-iris` + `sqlalchemy-iris` work; IRIS just isn't in Superset's own docs list. |
| **Apache Airflow** | ⚠️ `airflow-provider-iris` exists (IrisSQLOperator, IrisSensor) but off-registry and flagged "Issue Detected". |
| **n8n** | ⚠️ Community node exists. |
| **KNIME** | ⚠️ Works over JDBC, community-documented. |
| **MCP** | ⚠️ AI Hub MCP server (2026.x) + community `mcp-server-iris`. Technically ahead; invisible in directories. |

The ⚠️ rows are the cheap ones. Each is an existing working integration that needs
hardening, an InterSystems maintainer, and a catalog submission — not a build.

---

## Two structural findings worth escalating

### The SEO asymmetry is actively being monetized against InterSystems

Matillion's connector page — *"InterSystems IRIS to Databricks — Connect & Load Data
in Minutes"* — and CData's equivalents rank for `InterSystems IRIS` + competitor
queries. CData Virtuality publishes an "InterSystems Caché → Azure Synapse" page.
Third-party integrators have correctly identified "get data out of IRIS into a
warehouse" as a commercially valuable search intent, and they own those results
because InterSystems publishes no competing page.

There is no connector to build here. The fix is content: InterSystems-owned pages for
`IRIS + Snowflake`, `IRIS + Databricks`, `IRIS + Fabric` that make the
*federate/don't-copy* argument, so the buyer researching that question finds the
InterSystems framing first.

### `iris-pgwire` is an under-exploited force multiplier

`intersystems-community/iris-pgwire` implements the PostgreSQL wire protocol in front
of IRIS. PostgreSQL is a named, first-class source in essentially every platform on
this list — Fivetran, Airbyte, Lakehouse Federation, Lakeflow Connect, Fabric
mirroring, Looker, Sigma, Omni, Hightouch, Census.

If InterSystems productized and certified pgwire, a meaningful fraction of these gaps
could be closed *without building a single connector* — connect as Postgres, work
today. It won't earn a branded IRIS tile (which is much of the marketing value), so
it is complementary to, not a replacement for, the Tier 1 work. But as a stopgap that
unblocks field deals while proper connectors are built, nothing else on this list has
comparable leverage per dollar.

**Action:** evaluate promoting `iris-pgwire` from community project to supported
feature, and quantify which of these 23 platforms it unblocks as-is.

---

## Recommended build order

| Order | Item | Why first |
| --- | --- | --- |
| 1 | Publish the Grafana plugin | Code exists, 35M-user surface, weeks of work |
| 2 | Submit IRIS MCP server to agent directories | Code exists, fastest-moving surface, early-mover advantage |
| 3 | Adopt the orphaned community integrations | `dbt-iris`, `superset-iris`, `airflow-provider-iris`, `n8n-nodes-iris` — put an InterSystems maintainer on each, clear the "Issue Detected" flags, get each into its host catalog |
| 4 | Build the Fivetran partner connector | Flagship modern-data-stack proof point; both parties have formally declined, so nobody else will |
| 5 | Ship IRIS+competitor content pages | Reclaims the SERP from Matillion and CData; zero engineering |
| 6 | Open partnership motions on Fabric mirroring and Salesforce Zero Copy | Long lead times — start the clock now |
| 7 | Evaluate productizing `iris-pgwire` | Potentially closes a dozen gaps at once as a stopgap |

Items 1–3 are all "publish what exists." Nothing in the top three requires new
engineering, which is the most actionable conclusion in this document.

---

## Confidence and limitations

- **High confidence** (directly sourced this session): Fivetran, Grafana catalog,
  Airbyte, Databricks Lakehouse Federation, Lakeflow Connect, Fabric mirroring,
  Salesforce Zero Copy, Confluent Hub, Power BI, Datadog, DBeaver, DataGrip,
  Metabase, Superset, Airflow, n8n, dbt, Matillion, MCP servers, Sigma, Omni.
- **Medium confidence** (inferred from partial evidence — verify before citing
  externally): Atlan/Collibra/Alation specifics, Hightouch/Census, Looker's full
  dialect list, AWS Glue/DMS/Athena named endpoints, Zapier/Make/Workato,
  Trino, Terraform, and the long-tail row.
- **Not verified:** the T column (see scoring caveat), and the exact current status of
  connectors on platforms that ship frequently. Integration catalogs change monthly;
  re-verify anything load-bearing before it goes into a deck.

## Sources

- [Fivetran Support — New Connector: InterSystems IRIS](https://support.fivetran.com/hc/en-us/community/posts/37966707693207-New-Connector-InterSystems-IRIS)
- [InterSystems Ideas — Implement support to Fivetran (DPI-I-449)](https://ideas.intersystems.com/ideas/DPI-I-449)
- [InterSystems Ideas — Implement IRIS connector for Airbyte (DPI-I-447)](https://ideas.intersystems.com/ideas/DPI-I-447)
- [caretdev/grafana-intersystems-datasource](https://github.com/caretdev/grafana-intersystems-datasource)
- [Grafana support for InterSystems IRIS — Developer Community](https://community.intersystems.com/post/grafana-support-intersystems-iris)
- [Grafana Labs crosses 10,000 customers / $600M ARR](https://grafana.com/press/2026/08/26/grafana-labs-crosses-10000-customer-milestone-as-ai-adoption-accelerates-growth-across-the-platform/)
- [Databricks — What is query federation? (Lakehouse Federation)](https://docs.databricks.com/aws/en/query-federation/database-federation)
- [Databricks — What is Lakeflow Connect?](https://docs.databricks.com/aws/en/ingestion/overview)
- [Microsoft — Mirroring in Microsoft Fabric documentation](https://learn.microsoft.com/en-us/fabric/mirroring/)
- [Salesforce — Zero Copy Partner Network announcement](https://www.salesforce.com/news/press-releases/2024/04/25/zero-copy-partner-network/)
- [Snowflake — Snowflake-managed MCP server](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp)
- [Databricks — Model Context Protocol on Databricks](https://learn.microsoft.com/en-us/azure/databricks/generative-ai/mcp/)
- [InterSystems — AI Hub MCP Server](https://docs.intersystems.com/components/csp/docbook/DocBook.UI.Page.cls?KEY=BAIHUB_mcp)
- [caretdev/mcp-server-iris](https://github.com/caretdev/mcp-server-iris)
- [InterSystems — Certified IRIS connector for Power BI](https://www.intersystems.com/news/intersystems-releases-certified-intersystems-iris-data-platform-connector-for-microsoft-power-bi/)
- [InterSystems Docs — Connect IRIS data to Power BI](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=APOWER)
- [Datadog — Add InterSystems IRIS integration (integrations-core PR #24690)](https://github.com/DataDog/integrations-core/pull/24690)
- [Matillion — InterSystems IRIS to Databricks connector](https://www.matillion.com/connectors/intersystems-iris/databricks)
- [intersystems-community/iris-pgwire](https://github.com/intersystems-community/iris-pgwire)
- [dbt — Supported data platforms](https://docs.getdbt.com/docs/supported-data-platforms)
- [dbt Community — dbt-iris adapter for InterSystems IRIS](https://discourse.getdbt.com/t/dbt-iris-adapter-for-intersystems-iris-data-platform/8690)
- [Apache Superset now with IRIS — Developer Community](https://community.intersystems.com/post/apache-superset-now-iris)
- [Metabase IRIS Driver — Developer Community](https://community.intersystems.com/post/metabase-iris-driver)
- [Metabase — community drivers list](https://github.com/metabase/metabase/blob/master/docs/developers-guide/community-drivers.md)
- [InterSystems IRIS provider for Apache Airflow — Developer Community](https://community.intersystems.com/post/intersystems-iris-provider-apache-airflow)
- [n8n-nodes-iris — Open Exchange](https://openexchange.intersystems.com/package/n8n-nodes-iris)
- [confluent-kafka-iris — Open Exchange](https://openexchange.intersystems.com/package/confluent-kafka-iris)
- [Confluent Hub](https://www.confluent.io/hub/)
- [DBeaver officially supports InterSystems IRIS — Developer Community](https://community.intersystems.com/post/dbeaver-officially-supports-intersystems-iris)
- [JetBrains DataGrip — databases with basic support](https://www.jetbrains.com/help/datagrip/other-databases.html)
- [Tableau Exchange — Connectors](https://exchange.tableau.com/en-us/connectors)
- [Looker dialects](https://docs.cloud.google.com/looker/docs/dialects)
- [Atlan — Supported sources](https://ask.atlan.com/hc/en-us/articles/7241035988113-Supported-sources)
- [Alation — All connectors](https://www.alation.com/product/connectors/all-connectors/)
- [Hightouch — Sources overview](https://hightouch.com/docs/sources/overview)
- [Airbyte — Sources](https://docs.airbyte.com/integrations/sources)
- [Airbyte usage and growth statistics 2026](https://fueler.io/blog/airbyte-usage-revenue-valuation-growth-statistics)
- [Alteryx Community — InterSystems Caché database](https://community.alteryx.com/discussion/491082/intersystems-cache-database)
- [Omni — Best BI tools for Snowflake teams 2026](https://omni.co/articles/best-bi-tools-for-snowflake-teams-2026)
- [OpenAI ChatGPT Work Data Agent — BigQuery, Snowflake, Databricks](https://www.datastudios.org/post/openai-data-agent-chatgpt-work-bigquery-snowflake-databricks)

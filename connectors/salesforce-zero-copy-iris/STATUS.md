# STATUS — Salesforce Zero Copy / IRIS

Environment constraints that bound every claim below: no running IRIS, no Docker
daemon, no Salesforce org, no vendor accounts created or contacted (per this task's
HARD RULES). Additionally, this session's outbound web-fetch tool was blocked by the
network egress proxy for every content domain tried, including `salesforce.com`,
`help.salesforce.com`, `developer.salesforce.com`, `cio.com`, `salesforceben.com`,
`businesswire.com`, `medium.com`, and even `en.wikipedia.org`. All web research below
therefore comes from **search-engine result snippets that quote primary-source pages**
(Salesforce press releases, `developer.salesforce.com` and `help.salesforce.com`
documentation, Salesforce's own product pages), not from directly-fetched full pages.
Where a claim rests only on a snippet rather than a page Claude read in full, it is
marked so.

---

## VERIFIED

Backed by pasted real command output, or by a search-engine snippet that quotes the
named primary source directly (URL given in each case).

- **The odata_iris test suite passes, in full, in this environment, with no
  dependencies beyond the Python standard library and pytest.** Real output:

  ```
  $ cd connectors/salesforce-zero-copy-iris && python3 -m pytest -q
  ..........................................................               [100%]
  58 passed in 0.05s
  ```

  Environment: Python 3.11.15, pytest 9.1.1 (both already present in this container;
  verified with `python3 --version` → `Python 3.11.15` and `python3 -m pytest
  --version` → `pytest 9.1.1`).

- **The Zero Copy Partner Network launched April 25, 2024, at Salesforce World Tour
  NYC, with AWS, Databricks, Google Cloud, and Snowflake; Microsoft joined later.**
  Source: Salesforce press release, "Salesforce Unveils Zero Copy Partner Network...",
  https://www.salesforce.com/news/press-releases/2024/04/25/zero-copy-partner-network/
  (quoted via search snippet).

- **Each named partner's zero-copy mechanism is different and was engineered per
  partner, not through one shared spec** — Snowflake via Snowpark Container Services +
  Iceberg; Databricks via a Delta→Iceberg bridge; BigQuery via BigQuery's Iceberg
  Metastore; Redshift via AWS Glue Data Catalog query federation; Microsoft Fabric via
  Lakehouse file sharing. Sources: Salesforce Ben and CIO.com coverage (quoted via
  search snippets); Microsoft's own docs at
  https://learn.microsoft.com/en-us/azure/databricks/query-federation/salesforce-data-cloud-file-sharing
  (title/summary only, via snippet).

- **Data 360 (Data Cloud) has a distinct, generic OData Connector, currently Beta, that
  is explicitly documented as supporting both batch ingestion AND "Zero Copy (Query
  Federation) Data Federation."** This is the single most important finding of this
  research and the basis for the recommendation. Source:
  `developer.salesforce.com/docs/data/data-cloud-int/guide/c360-a-odata-connector.html`
  ("OData Connector | Data 360 Integrations | Data 360 Integration Guide | Salesforce
  Developers"), quoted via search snippet, including the verbatim beta-terms sentence
  ("This feature is a Beta Service. A customer may opt to try a Beta Service in its
  sole discretion...") and a support contact
  (`datacloud-connectors-beta@salesforce.com`). Corroborating page:
  `developer.salesforce.com/docs/data/data-cloud-int/guide/c360-a-set-up-odata-connection.html`
  ("Set Up an OData Connection").

- **The Data 360 OData Connector's setup flow is generic** (service root URL, OData
  producer requirement, Basic or Named-Credential/OAuth authentication, optional SSL
  cert upload, firewall/IP allowlisting for Salesforce's outbound calls) — i.e., nothing
  in the setup flow is specific to a named partner. Source:
  `developer.salesforce.com/docs/data/data-cloud-int/guide/c360-a-create-odata-data-stream.html`
  and `.../c360-a-set-up-odata-connection.html` (quoted via search snippets).

- **Salesforce Connect (the Core Platform / Sales Cloud & Service Cloud feature) is a
  separate product surface from Data Cloud/Data 360**, supports OData 2.0, 4.0, and
  4.01 adapters, and materializes results as "external objects" consumed by CRM
  features (Lightning reports, flows) — not Data Model Objects in Data 360. Source:
  `help.salesforce.com` OData adapter documentation pages, e.g.
  `platform_connect_add_external_data_source.htm` and `odata_adapter_about.htm` (quoted
  via search snippets). This confirms the task's prior: **Salesforce Connect OData is
  not, by itself, "Data Cloud zero copy."**

- **Data 360's Apache Iceberg / Parquet File Federation requires the source data to
  already exist as Iceberg V1 tables in object storage** (a publicly accessible or
  VPC-scoped S3 bucket, or an Azure equivalent), read directly by Data 360's query
  engine without a further copy into Data 360 itself. Source:
  `developer.salesforce.com/docs/data/data-cloud-int/guide/c360-a-set-up-apacheiceberg-file-fed-connection.html`
  and Salesforce's own engineering blog,
  `engineering.salesforce.com/inside-data-clouds-open-lakehouse-4m-tables-and-50pb-powered-by-apache-iceberg/`
  (quoted via search snippets).

- **The Data 360 Ingestion API is explicitly a physical-ingestion (bulk-copy) API** —
  CSV-based bulk upsert/delete jobs, or a streaming pattern that batches updates roughly
  every 3 minutes — and Salesforce's own materials contrast it with zero copy rather
  than presenting it as an instance of zero copy. Source:
  `developer.salesforce.com/docs/data/data-cloud-int/references/data-cloud-ingestionapi-ref/`
  pages (quoted via search snippets).

- **The MuleSoft Anypoint Connector for Data Cloud is positioned around ingestion and
  reverse-ETL, not query federation.** Source: MuleSoft's own blog,
  `blogs.mulesoft.com/news/data-cloud-and-mulesoft/` (quoted via search snippet).

- **InterSystems/IRIS does not appear in any Zero Copy Partner Network partner list**
  found in this research (searched directly; no result connected the two). This matches
  `research/ecosystem-connector-gaps.md`'s framing of this as gap #6 in this repo.

- **IRIS has no native OData producer.** The community project "OData Server for IRIS"
  (published on InterSystems Open Exchange /
  `github.com/yurimarx/isc-iris-odata`) wraps IRIS `%Persistent` classes with a
  *separate* Java microservice built on Apache Olingo (OData v4 reference
  implementation) + Spring Boot — i.e., a bolt-on adapter, not a built-in IRIS
  capability. Source: `community.intersystems.com/post/odata-server-intersystems-iris`
  and the linked GitHub repo (quoted via search snippet).

- **General Salesforce ISV/technology partner onboarding is a commercial-agreement +
  security-review process, not a connector SDK submission.** Source:
  `salesforce.com/partners/become-an-isv-partner/` (quoted via search snippet: "join the
  Partner Community... sign the commercial agreement... complete a thorough security
  review").

## UNVERIFIED

Things this research could not confirm to the standard above, or that rest on weaker
evidence than the VERIFIED section.

- **No full primary-source page was read directly.** Every citation above is a
  search-engine snippet of a primary source, not a page this session fetched and read
  in full — `WebFetch` was blocked by the network egress proxy for every domain tried
  (see the top of this file). Direct fetches should be re-attempted from an environment
  without this restriction before this document is treated as a final authority, though
  the developer.salesforce.com URLs, page titles, and quoted sentences are specific
  enough (including an internal beta-support email address) that they are very unlikely
  to be search-snippet hallucination.
- **Exact OData version(s) the Data 360 OData Connector requires (2.0 vs 4.0 vs 4.01)
  for Zero Copy Query Federation specifically** is not confirmed — the version list
  found (2.0/4.0/4.01) is documented for classic Salesforce Connect; the Data 360
  connector's own page did not surface a version requirement in the snippets retrieved.
  This repo's `odata_iris` package targets OData v4 (CSDL/EDMX `$metadata`, v4 URL
  conventions) as the safer, more current target, but this should be confirmed against
  the actual Data 360 connector documentation (or, better, empirically once test access
  to a Data 360 org exists) before depending on it.
- **Whether the Data 360 OData Connector's Zero Copy Query Federation mode does true
  per-request live query pushdown with no server-side caching, or caches results for
  some period** is unconfirmed. One search snippet ("Zero Copy acceleration enables the
  caching of external data within Data Cloud...") suggests Data Cloud may cache query
  results for performance, which would be a nuance on "zero copy" worth confirming — it
  would still avoid a *persistent, admin-visible duplicate table*, but "zero copy" and
  "zero caching" are not necessarily the same claim.
- **Whether Beta-tier features of Data 360 carry any restriction on production use,
  support commitments, or availability by Salesforce edition/region** is unconfirmed —
  standard Salesforce Beta Services Terms were referenced in a snippet but not read in
  full.
- **Whether this repo's `odata_iris` package's generated OData v4 `$metadata` document
  and query semantics are accepted as-is by Data 360's OData Connector, or need
  connector-specific adjustments** (e.g., specific capability annotations, a particular
  auth flow, pagination conventions) is unverified — there is no Data 360 org available
  in this environment to test against, and no InterSystems IRIS instance to serve real
  data through this package's SQL layer.
- **Whether IRIS's SQL dialect handles the exact `SELECT TOP n col FROM table [WHERE
  ...] [ORDER BY ...]` shape this package generates without further adjustment** is
  unverified against a live IRIS instance (none available in this environment); it is
  consistent with published IRIS SQL syntax but not executed here.

## HUMAN ACTIONS REQUIRED

For the partnership motion (getting InterSystems into the *named* Zero Copy Partner
Network):

1. **Identify the business owner.** This is a partnerships/alliances function, not
   engineering — likely InterSystems' ISV Alliances or Healthcare/Life Sciences
   partnerships team, given the Salesforce Health Cloud adjacency called out in
   `research/ecosystem-connector-gaps.md`.
2. **Enroll in the Salesforce Partner Program** (`salesforce.com/partners/become-an-isv-partner/`
   or the general partner program) as a first step — join Partner Community, review the
   commercial agreement appropriate to the intended relationship, and be prepared for a
   security review.
3. **Target a joint customer or joint press moment**, per the ecosystem-gaps research
   doc's own recommendation for this and the similar Databricks/Fabric gaps: a shared
   provider/payer account running both IRIS and Salesforce Health Cloud is the natural
   lever to get a Salesforce product-team conversation started, since the existing five
   partners all got bespoke engineering attention.
4. **Get an explicit answer from Salesforce on whether the Zero Copy Partner Network is
   still accepting new named members**, and if so what the current technical/commercial
   bar is — this was not published anywhere found in this research, which itself may
   mean the program is closed to new entrants absent a strategic push from Salesforce's
   side.
5. **Decide whether "in the Partner Network" is even the right ask** versus quietly
   shipping and documenting the OData Zero Copy Query Federation path below — the latter
   delivers the customer value (IRIS data in Data 360 without bulk copy) without needing
   Salesforce's permission at all, at the cost of no co-marketing.

For the technical path (Data 360 OData Connector / Zero Copy Query Federation), before
this goes further than the offline package in this repo:

6. **Get a Data 360 (Data Cloud) trial/sandbox org** and independently confirm the
   OData Connector's exact requirements — OData version, capability annotations,
   pagination behavior, auth options — directly from the product UI/docs (this session
   could not fetch `developer.salesforce.com` pages directly; a human with normal web
   access should re-verify every citation in this file's VERIFIED section against the
   full page, not just the snippet).
7. **Stand up `odata_iris` against a real IRIS instance** (this repo's shared
   `intersystems-irispython` DB-API driver, per `../README.md`) behind an HTTP layer
   (WSGI/ASGI, or an IRIS-native CSP REST handler) and confirm Data 360 can actually
   configure it as a Zero Copy Query Federation source end to end.
8. **Confirm the Beta program's terms** (`datacloud-connectors-beta@salesforce.com` per
   the snippet found) — Beta features can change or be withdrawn, which matters before
   anyone represents this path as durable/production-ready externally.

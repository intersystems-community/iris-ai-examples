# Salesforce Zero Copy — IRIS

**Verdict: partially blocked, partially implementable — and the two halves are easy to
confuse with each other.**

- **Getting IRIS into the branded "Zero Copy Partner Network"** (the program with the
  press release, the co-marketing tile, Dreamforce presence) **is blocked**. It has no
  public partner spec a vendor can implement unilaterally. Every launch member
  (Snowflake, Databricks, Google BigQuery, Amazon Redshift, later Microsoft Fabric) got
  in through bespoke, Salesforce-side joint engineering, and the network's own
  onboarding path is the general Salesforce ISV/technology-partner program, not a
  connector SDK. This part is a business-development task. See VERDICT #1 below.
- **Getting IRIS data into Data Cloud (now "Data 360") without bulk-copying it is not
  blocked.** Data Cloud ships a second, unbranded, protocol-generic mechanism —
  the **OData Connector**, in Beta, explicitly documented as supporting **"Zero Copy
  (Query Federation) Data Federation"** — that any system exposing a standards-compliant
  OData v4 service can use, no partnership required. IRIS is not a native OData
  producer, so this repo builds the missing piece: a minimal OData v4 producer over IRIS
  SQL. See VERDICT #2 and the implementation below.
- These are **not the same accomplishment**. Building the OData producer does **not**
  get InterSystems into the Zero Copy Partner Network, does not earn a partner-directory
  tile, and is not co-marketed. It is a real, standards-based, zero-copy-in-the-technical-sense
  path into Data Cloud that InterSystems (or a customer) can stand up today without
  Salesforce's involvement. Label it as such — this document does, and so does the code
  (`odata_iris/__init__.py`).

Read `STATUS.md` for exactly what is cited-and-verified vs. inferred, and for the human
actions required for the partnership half.

---

## 1. What the Zero Copy Partner Network actually is

Salesforce launched the **Zero Copy Partner Network** on April 25, 2024, with AWS
(Redshift), Databricks, Google Cloud (BigQuery), and Snowflake; Microsoft (Fabric)
joined later. [Salesforce press release, Apr 25 2024](https://www.salesforce.com/news/press-releases/2024/04/25/zero-copy-partner-network/)
(fetched via search-engine cache of the primary source; direct fetch was blocked in this
environment — see STATUS.md "UNVERIFIED").

Each named partner's integration is a **different, bespoke connection method**, not one
shared spec:

| Partner | Mechanism (as reported) |
| --- | --- |
| Snowflake | query federation via Snowpark Container Services + Iceberg tables, plus data sharing |
| Databricks | Delta Lake → Iceberg bridge (query + file federation), plus data sharing |
| Google BigQuery | BigQuery Iceberg Metastore, query federation + data sharing |
| Amazon Redshift | query federation via AWS Glue Data Catalog |
| Microsoft Fabric | file sharing / Lakehouse Federation |

That heterogeneity is itself evidence there is no single "Zero Copy Partner Network
API" a vendor implements to join — Salesforce built (or co-built) each of these with the
named partner individually. The Zero Copy Partner Network's own composition —
database/data-set partners (Dun & Bradstreet, Moody's, ZoomInfo, Workday, The Weather
Channel) and SI partners (Accenture, Capgemini, Cognizant, Deloitte Digital, IBM, PwC,
Slalom, Wipro) — is likewise a curated partner roster, not a self-serve registry. No
public technical specification, certification test suite, or connector SDK for "become
a Zero Copy Partner Network member" surfaced in this research; the closest thing that
exists is Salesforce's general [ISV/technology partner program](https://www.salesforce.com/partners/become-an-isv-partner/)
(join Partner Community → sign a commercial agreement → security review), which is a
business relationship, not an engineering deliverable.

InterSystems / IRIS does not appear anywhere in this program. Confirmed by direct search
(see STATUS.md).

**Conclusion for #1: onboarding to the named, co-marketed Zero Copy Partner Network is
entirely Salesforce-side. There is nothing here a vendor can build its way into.**

## 2. The alternatives, evaluated — which is actually zero copy

Salesforce Data Cloud (rebranded **Data 360**) has several distinct data-access
mechanisms. They get talked about interchangeably in marketing, which is exactly the
trap this task's brief warned about. Sorted from "real zero copy, unilaterally
buildable" to "sounds like zero copy, isn't":

| Mechanism | Is it zero copy relative to IRIS? | Can a vendor build it unilaterally? | Verdict |
| --- | --- | --- | --- |
| **Data 360 OData Connector — Zero Copy Query Federation (Beta)** | **Yes.** Data 360 sends a query, the OData producer runs it live against IRIS SQL, results stream back. No persistent duplicate of IRIS data anywhere. | **Yes.** It's a generic OData v4 client inside Data 360; any compliant producer works. No partner agreement needed. | **This is the real, implementable answer.** Beta, unbranded, not co-marketed. |
| Salesforce Connect external objects (OData 2.0/4.0/4.01) | Yes, in the sense that no copy is made — but this is a **Core Platform / Sales Cloud & Service Cloud** feature (external objects, Lightning reports), **not Data Cloud**. It does not populate a Data Model Object, does not participate in Data 360's identity resolution/Calculated Insights/segments. | Yes — same generic OData mechanism, older and GA. | Real zero-copy access to CRM records, but **does not satisfy "Data Cloud zero copy."** Confirms this task's prior suspicion: Salesforce Connect ≠ Data Cloud. |
| Data 360 Apache Iceberg / Parquet File Federation (BYOL) | **No, relative to IRIS.** Data 360 reads Parquet-formatted Iceberg tables directly from S3/Azure Blob without further copying — but IRIS data must first be exported/converted into Iceberg-formatted files and land in object storage. That export is a bulk copy; Data 360 just doesn't make a *second* one. | Technically yes (any vendor can write Iceberg to S3) — but this reintroduces exactly the ETL step "zero copy" is sold as avoiding. | **Mislabel risk.** This is the option the task specifically warned about; it is a zero-copy *read* on top of a bulk-copy *write*. Not recommended as "the zero-copy answer" for IRIS. |
| Data 360 Ingestion API (streaming or bulk) | **No.** Explicitly a physical-ingestion API: CSV bulk upsert jobs or a ~3-minute micro-batch streaming pattern, both writing a durable copy into the Data 360 Data Lake. | Yes, trivially (it's just a REST API), but building this proves nothing about zero copy. | Ordinary ETL/ELT. Do not present this as zero copy. |
| MuleSoft Anypoint Connector for Data Cloud | **No.** Built for CRM-data ingestion into Data 360 and reverse-ETL out; Salesforce's own MuleSoft blog frames it as feeding the ingestion pipeline, not as a federation layer. | N/A — this is Salesforce/MuleSoft tooling, not something IRIS "joins." | Not a candidate. |

**Recommendation: build against the Data 360 OData Connector's Zero Copy Query
Federation path**, because it is the only option that is (a) genuinely zero-copy
relative to IRIS's live data and (b) implementable without Salesforce's participation.
Its caveats — it is Beta, it is not part of the co-marketed partner list, and Salesforce
could change or discontinue it — are real and are called out in STATUS.md, not hidden.

IRIS has no native OData producer (confirmed: community tooling like `OData Server for
IRIS` wraps IRIS `%Persistent` classes with a separate Apache Olingo/Spring Boot Java
microservice — not a built-in IRIS capability). This repo's `odata_iris/` package is a
minimal, from-scratch, Python implementation of the missing piece, built directly
against IRIS SQL via the DB-API surface this repo already documents
(`intersystems-irispython`).

## 3. What was built

`odata_iris/` — a small, dependency-free (stdlib only) Python package:

| File | Responsibility |
| --- | --- |
| `schema.py` | Declares `Column` / `EntitySet` / `Schema` — the whitelist of IRIS tables and columns exposed. Nothing downstream trusts a client-supplied identifier unless it's in here. |
| `metadata_xml.py` | Builds the OData v4 `$metadata` document (CSDL/EDMX: `EntityType`, `Key`, `Property`, `EntityContainer`/`EntitySet`) from a `Schema`. |
| `query_translate.py` | Translates `$select`, `$filter`, `$top`, `$skip`, `$orderby` into a parameterized IRIS SQL `SELECT`. Hand-written recursive-descent parser for the `$filter` subset (`eq/ne/gt/ge/lt/le`, `and/or/not`, parens, `contains/startswith/endswith`, `null`). |
| `dbapi.py` | A PEP 249-shaped `Connection`/`Cursor` `Protocol` — the seam. Production code hands this `iris.connect(...)`; tests hand it a fake. |
| `service.py` | Wires schema + translation + a `Connection` into `get_metadata_document()` and `query_entity_set()`. No HTTP framework — see "What this is not," below. |

**Injection safety, precisely:** column/property names from the client are only ever
placed in SQL text after an exact-match check against the entity set's declared column
whitelist (`schema.EntitySet.column_names`); anything else raises before any SQL is
built. Literal values are never interpolated — they go into a `params` list bound via
`?` placeholders. `$top`/`$skip` are validated with a strict `^\d+$` regex before
`int()`, then embedded as plain integers (IRIS's `TOP` clause doesn't take a bind
parameter in that position in all drivers, so the safety property there is "only ever a
value that passed a digits-only regex," not parameterization).

### What this is not

- **Not a running service.** There is no IRIS instance, no Docker daemon, and no
  Salesforce org available in this environment (per this task's HARD RULES), so nothing
  here is proven against a live IRIS or a live Data 360 tenant. `service.py` is a
  library; wiring it to `iris.connect(...)` and an HTTP layer (WSGI/ASGI, or a CSP REST
  handler inside IRIS itself) is the next step for a human with a container.
- **Not Salesforce Connect.** This targets the Data 360 OData Connector's Zero Copy
  Query Federation path, which is a different product surface from core-platform
  external objects (though the wire protocol — OData — is the same, so the same
  `$metadata`/`$filter` translation would also serve a Salesforce Connect external data
  source if someone wanted that instead).
- **Not membership in the Zero Copy Partner Network.** Restated because it's the
  single easiest thing to overclaim here: standing this service up in front of a real
  IRIS instance would let a Data 360 admin configure IRIS as a Zero Copy Query
  Federation source. It would not put InterSystems on
  `salesforce.com/data/zero-copy-partner-network/`, in a press release, or on an
  AppExchange tile. Only Salesforce controls that list.

## Running the tests

```bash
cd connectors/salesforce-zero-copy-iris
python3 -m pytest -q
```

No dependencies beyond `pytest` (already present in this environment) and the Python
standard library — no IRIS, no Docker, no network, no API key. See `STATUS.md` for the
pasted, real output of this exact command.

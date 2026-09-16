# Publishing paths: getting an IRIS tile into Microsoft Fabric

Two genuinely different routes exist. They are not competitors — Open
Mirroring is available immediately and unilaterally; native mirrored-source
status is a longer-term, higher-ceiling goal that depends on Microsoft.

## Route 1 — Open Mirroring (what this directory implements)

**What it is:** any application writes Parquet change files into a OneLake
landing zone URL that Fabric hands out when you create an "open mirrored
database." No Microsoft code review, no partner program, no listing
anywhere is required to make it work technically.
([`open-mirroring.md`](https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring))

**Who controls it:** InterSystems (or any customer/partner) entirely. No
Microsoft approval gate to *build* it.

**What it does NOT get you by default:**
- No entry in Fabric's own "supported sources" table
  ([`overview.md`](https://learn.microsoft.com/en-us/fabric/mirroring/overview)
  — the table this connector confirmed does not list IRIS and would not
  list it just because an Open Mirroring publisher exists).
- No Microsoft co-marketing, no "Mirror your IRIS data" wizard entry point
  inside the Fabric portal next to Snowflake/Databricks/etc.
- No guarantee of forward compatibility beyond what's documented — Open
  Mirroring is a contract with the landing-zone file format, not a
  supported-partner-connector SLA.

**What it DOES get you:**
- A real, working, IRIS -> Fabric data path today, buildable and shippable
  entirely by InterSystems or a customer, matching the pattern of e.g.
  Business Central's `bc2adls` community/ISV integration with Open
  Mirroring.
- A concrete answer the next time a Microsoft-shop healthcare account asks
  "can I get my IRIS data into Fabric without an ETL hop through Snowflake
  or Databricks?"
- A reference implementation InterSystems could publish (as a GitHub repo,
  a docs page, a Fabric Community post) to start owning some of the search
  real estate the ecosystem-gaps research flagged as ceded to third parties
  (Matillion, CData, etc. — see `../research/ecosystem-connector-gaps.md`).

**Effort:** low-to-moderate, no Microsoft dependency. This directory is a
working reference implementation of the Parquet/metadata side; the only
missing piece for a production deployment is the OneLake upload transport
(Blob/ADLS Gen2 API calls with Fabric-scoped Azure credentials) and a real
IRIS change-tracking mechanism (see `README.md` design decision 6 and
`STATUS.md`).

## Route 2 — Native mirrored source (Microsoft builds/certifies it)

**What it is:** IRIS gets added to the same list Snowflake, Databricks,
Oracle, SAP, and Cosmos DB are on today
([`includes/mirrored-sources-table.md`](https://github.com/MicrosoftDocs/fabric-docs/blob/main/docs/mirroring/includes/mirrored-sources-table.md)),
with a first-class "Mirror InterSystems IRIS" entry point in the Fabric
portal, built either by Microsoft directly or by InterSystems under a
Microsoft partner/certification program comparable to how Snowflake's and
Databricks' own mirroring integrations were built.

**Who controls it:** Microsoft. This is a joint-engineering motion, not
something InterSystems can ship unilaterally — it requires a partnership
agreement, almost certainly a technical review/certification process
analogous to other Fabric/Power Platform certified-connector programs, and
Microsoft product-team prioritization.

**What it gets you that Route 1 doesn't:**
- The actual catalog-presence win the ecosystem-gaps research is chasing:
  a branded tile, discoverability inside the Fabric portal itself, and the
  "is it in Fabric?" procurement-question answer being unambiguously yes.
- Likely better performance/latency characteristics than a file-drop
  landing zone, since a native source can use change-tracking mechanisms
  Microsoft builds directly against the source engine rather than an
  application-level convention.

**Effort:** high, and not solely InterSystems's to control — this is the
"E: 5, requires the other vendor to build it" case from
`../research/ecosystem-connector-gaps.md`'s scoring.

## Precedent: the certified Power BI connector

InterSystems has already been through a materially similar process once —
this is the strongest existing evidence that a Microsoft-certified
integration for IRIS is achievable, and the natural relationship to point
to when proposing Route 2:

> InterSystems announced a **certified InterSystems IRIS Data Platform
> Connector for Microsoft Power BI** in April 2019, giving Power BI users
> native access to IRIS relational tables and BI cubes, shipped as part of
> Power BI Desktop.

Sources (news/community, not Microsoft Learn — cited as historical
precedent, not as a landing-zone spec claim):
[InterSystems press release](https://www.intersystems.com/news/intersystems-releases-certified-intersystems-iris-data-platform-connector-for-microsoft-power-bi/),
[InterSystems Developer Community write-up](https://community.intersystems.com/post/power-bi-connector-intersystems-iris-part-i).
The connector's current docs page is
[docs.intersystems.com APOWER](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=APOWER)
— found via search; this session could not fetch its content directly
(`docs.intersystems.com` is blocked by this sandbox's egress proxy, same as
for the type-mapping table in `README.md` — see `STATUS.md`), so treat its
current content as unverified here even though the connector's existence is
well documented elsewhere.

That precedent establishes InterSystems already has a working relationship
with Microsoft's certified-connector process for at least one Microsoft
product surface (Power BI). It is evidence the Route 2 motion is
*achievable*, not evidence that Fabric mirroring specifically is already in
motion — no source found in this session indicates IRIS is on Microsoft's
Fabric mirroring roadmap.

## Recommendation

Ship Route 1 now as the concrete, low-risk proof point (this directory is
that proof point), and use it as the opening argument for a Route 2
conversation with Microsoft's Fabric partner team — "we already built the
open, unilateral integration; here's the adoption/usage evidence; let's
talk about first-class support" is a stronger pitch than an unbuilt request.

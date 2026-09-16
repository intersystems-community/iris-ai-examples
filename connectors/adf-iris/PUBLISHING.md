# Getting a native IRIS connector into ADF / Fabric Data Factory

## Why this can't be done unilaterally

Snowflake, Databricks, and every other named ADF connector exist because
Microsoft's Data Factory team wrote and ships the linked-service type,
the connection UI, the driver bundling (or driver-download flow), and the
docs page as part of the ADF product itself. There is no public plugin
SDK, extension point, or partner-submission portal for adding a new
`"type"` to the ADF `LinkedService` union — the schema in `vendor/` is a
closed enum Microsoft controls. `az`, ARM, and ADF Studio all validate
against it. Nothing outside Microsoft can add to it. This is different
from, say, Grafana (an open plugin architecture) or Airbyte (an open
connector directory) — the comparison other connectors in
`../README.md`'s gap-ranking table can use, ADF cannot.

The only two routes to a native entry are:

1. **Microsoft builds it themselves**, the way they built the Snowflake
   and Databricks connectors — internal ADF team roadmap, InterSystems
   has no direct lever on this beyond making the case.
2. **A joint-engineering / ISV-partner motion** where InterSystems ships
   and maintains the connector logic under a Microsoft-sanctioned program,
   analogous to what happened with the Power BI connector (below). This is
   a business-development and engineering-partnership undertaking, not
   something achievable from a code repository.

## Precedent: the certified Power BI connector

InterSystems has already done the joint-engineering motion once, for a
different Microsoft product: a certified InterSystems IRIS connector for
Power BI, announced by InterSystems in 2019
(<https://www.intersystems.com/news/intersystems-releases-certified-intersystems-iris-data-platform-connector-for-microsoft-power-bi/>).
That connector:

- Uses the InterSystems ODBC driver under the hood for relational tables
  (the same driver this directory's templates depend on), plus a path to
  IRIS BI cubes (measures/dimensions) that ODBC alone doesn't expose.
- Was built as a **Power Query custom connector** (M language extension),
  which — unlike ADF's closed `LinkedService` enum — Power BI/Power Query
  *does* have a public, documented extensibility SDK for. This is the
  structural reason the Power BI connector was possible where a native ADF
  connector is not: Power Query has a real third-party connector SDK, ADF
  does not.
- Went through Microsoft's Power BI custom-connector certification
  program, which is how it ended up distributed *inside* Power BI Desktop
  rather than as a side-loaded extension — as of 2024 it's maintained as
  the "InterSystems Health Insight Connector for Power BI," per current
  InterSystems docs
  (<https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=APOWER>,
  fetch blocked by this session's egress proxy — cited, not independently
  re-verified this session).

**The relationship to ADF:** Power Query / Dataflow Gen2 is also how
Fabric Data Factory itself gets ODBC connectivity for one of its two
execution paths (see `README.md`'s Fabric section) — so a modernized,
IRIS-specific Power Query connector, if InterSystems chooses to invest in
one, would show up automatically as an available "Get Data" source inside
Fabric's Dataflow Gen2, without needing any ADF-specific engineering. That
is a real, actionable path that does not require Microsoft's ADF Copy
Activity team to do anything — it goes through the Power Query
extensibility SDK Microsoft already publishes.

**What a native ADF `LinkedService` entry (Copy Activity path, not
Dataflow Gen2) would additionally require, beyond the Power BI precedent:**

- Direct engagement with the Azure Data Factory product team (not the
  Power BI/Power Query team) — different org, different roadmap process.
- A driver InterSystems is willing to have Microsoft bundle, redistribute,
  or reference-install on self-hosted/managed IR hosts, with whatever
  licensing terms that requires.
- Conformance/certification testing against ADF's own connector test
  suite (not publicly documented in detail; Microsoft controls this).
- Ongoing maintenance commitment matching ADF's release cadence — a
  first-class connector implies ADF's team will file bugs, not just
  InterSystems noticing forum threads like the `-400` one in `README.md`.
- A named contact and case with Microsoft partner engineering (ISV
  Success Program / Azure Marketplace Technology Partner track are the
  typical entry points from the outside; which specific existing
  InterSystems-Microsoft partnership channel is the right one is a
  business relationship question this session cannot verify or assume).

## What this repo's templates are worth in the meantime

They make the *generic* path (ODBC + self-hosted IR) something a customer
can actually deploy and reproduce today, without needing any of the above.
That is a materially different, and much smaller, thing than a native
connector — see `README.md`'s scope statement — but it's the part that's
actually buildable without Microsoft's or InterSystems' further
engineering investment.

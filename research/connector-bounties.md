# Connector bounties — shortlist and briefs

*Draft for discussion.* Which connectors to offer as Global Masters bounties, what each
bounty asks for, and what DevRel must have in place before posting. Builds on
[`catalog-paths.md`](catalog-paths.md) and [`ecosystem-connector-gaps.md`](ecosystem-connector-gaps.md).

## Recommendation

- **Recommended: #1 — Get the IRIS data source plugin ready for the Grafana catalog.** M — a few weeks. Taker: Invite the author of `caretdev/grafana-intersystems-datasource` first.
- **Recommended: #9 — Get the IRIS source connector contribution-ready for Airbyte.** M — a few weeks. Taker: Open bounty; Python and Docker experience.
- **Recommended: #5 — Ship the IRIS → Microsoft Fabric Open Mirroring publisher.** M — a few weeks. Taker: Open bounty; Azure and Fabric experience.
- **Quick win: #17 — Get IRIS onto Apache Superset's list of supported databases.** S — days. Taker: Invite the author of `superset-iris` first.
- **Quick win: #12 — Assess dbt-iris against dbt's Trusted Adapter bar.** S — days. Taker: Invite the `dbt-iris` maintainer first.

## How the shortlist was chosen

| # | Candidate | Ends in a real listing | A community member can do it alone | Bounty-sized | Ranking score | Starts from working code | Verdict | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Grafana | Yes — DevRel signs and submits | Yes — Grafana OSS + IRIS CE | Yes — M | 9 | Yes — two plugins exist | **Recommended** | Top-ranked gap, one-click installs, and the work left is validation and polish. |
| 9 | Airbyte | Yes — community PR | Yes — Docker + IRIS CE | Yes — M | 7 | Yes — 72 tests | **Recommended** | Contribution-ready layout exists, and Estuary relists Airbyte connectors — one bounty, two catalogs. |
| 5 | Microsoft Fabric | Likely — Microsoft's Open Mirroring partner page | Yes — 60-day Fabric trial | Yes — M | 9 | Yes — writer built, upload missing | **Recommended** | Where much of the healthcare install base is heading, with a branded listing that needs no Microsoft engineering. |
| 17 | Apache Superset | Yes — docs generated on merge | Yes — open source | Yes — S | 5 | Yes — superset-iris | **Quick win** | One upstream pull request is both the code and the listing, and upstream maintains it afterwards. |
| 12 | dbt | Partial — Trusted status needs a DevRel maintenance commitment | Yes — dbt Core + IRIS CE | Yes — S, assessment only | 7 | Yes — dbt-iris | **Quick win** | A cheap assessment tells DevRel what Trusted status would actually cost before committing to it. |
| 4 | Fivetran | No — Partner-Built program closed | Partial — deploy needs an account | Yes — S | 9 | Yes — 75 tests | **Not now** | Highest impact, but the branded tile is closed to new partners; a bounty only buys a community-repo entry. Revisit if Fivetran reopens. |
| 10 | Confluent Hub | Partial — needs Confluent partner account | Yes — Kafka + IRIS CE | Yes — M | 7 | Yes — 57 tests on H2 | **Not now** | A good second-wave bounty for interoperability developers, once DevRel has the Confluent account and a security review lined up. |
| 7 | Tableau | Yes — Tableau Exchange | Partial — TDVT needs licensed Tableau Desktop on Windows | No — L | 8 | Yes — XSD-validated | **Not now** | TDVT is too large and too tool-bound for a bounty; better done in-house by the Power BI connector's owners. |
| 2 | AI agent directories | Yes — via AI Hub | No — AI Hub is an internal product | Yes — M | 10 | Yes — AI Hub server | **Not now** | The AI Hub team's job — the directories need InterSystems' own endpoint and domain verification. |
| 3 | Databricks, Snowflake, Salesforce, ADF | No — partnership-gated | Partial — paid or hard-to-get workspaces | Partial — M–L | 10 | Yes — recipes built | **Not now** | The listings depend on vendor partnerships, not on more code. |

- **Ends in a real listing:** Finishing it can put IRIS in the host's catalog without a vendor partnership.
- **A community member can do it alone:** Free tools, IRIS Community Edition, no InterSystems-owned accounts.
- **Bounty-sized:** One person, days to a few weeks.
- **Ranking score:** Traffic + impact out of 10, from the gap analysis.
- **Starts from working code:** Lower risk, faster to finish.

## What every bounty must deliver

DevRel will maintain these connectors after the bounty, largely with AI assistance. That only works when the code comes with tests that run against a real IRIS — an AI can keep a well-tested connector healthy, but it cannot tell whether an untested one still works.

- **Tests in two layers, both in CI.** Keep the offline suite passing, and add an integration suite that runs against IRIS Community Edition in Docker on every push (GitHub Actions).
- **An honest `STATUS.md`.** List what you verified, with evidence (command output, screenshots), and what you could not verify, with the reason.
- **A README quickstart someone else can follow.** DevRel will reproduce your result from it before accepting the work.
- **The agreed licence**, as a `LICENSE` file and in the package metadata.
- **No InterSystems logos.** Keep the placeholder icon; DevRel supplies approved branding at submission.
- **Stay available for the first review round** with the host's maintainers, for 30 days after acceptance.

## Bounty briefs

Written to be posted as-is. Each brief also carries the common requirements above.

### Get the IRIS data source plugin ready for the Grafana catalog

*Recommended · gap #1 · M — a few weeks · Invite the author of `caretdev/grafana-intersystems-datasource` first*

**Why it matters.** Grafana has more than 35 million users, and its plugin catalog installs data sources in one click. Snowflake and Databricks both have signed plugins there; InterSystems IRIS has none. This bounty takes an IRIS plugin from "builds and passes its unit tests" to "ready for Grafana's review".

**Where to start.** Two plugins already exist. `connectors/grafana-iris-datasource` in `intersystems-community/iris-ai-examples` is a Go backend over IRIS's REST/SQL API with SAM metrics and TypeScript editors; its unit tests pass but it has never run against a real IRIS. `caretdev/grafana-intersystems-datasource` uses IRIS's native protocol and streams SAM metrics. Pick one as the base and explain why, or merge them. The result must be a single plugin, not two.

**What you need.** Grafana OSS and IRIS Community Edition in Docker Compose; Go 1.24 and Node 22. Everything is free.

**What to deliver**

1. Run the plugin against live IRIS and fix whatever differs from its assumptions. The biggest known risk is the shape of the REST/SQL response, which was taken from forum posts and has never been checked.
2. Cover SQL queries across `%PosixTime`, NUMERIC precision and scale, `%Boolean`, NULLs and strings; the SAM-metrics query; and the health check, both passing and failing.
3. Add an integration suite that runs against IRIS Community in CI, alongside the existing offline tests.
4. Add end-to-end tests of the config editor, query editor and a dashboard panel, using Grafana's Playwright-based plugin e2e tooling.
5. Make Grafana's plugin validator pass with no errors, and clear high and critical `npm audit` findings and lint errors.
6. Provide a provisioned example dashboard (JSON) with SQL and SAM panels, plus screenshots of the config editor, query editor and dashboard for the catalog listing.

**Done when**

- [ ] CI is green on both the offline and live-IRIS suites.
- [ ] Grafana's plugin validator reports no errors.
- [ ] DevRel can bring up the example dashboard from the README in under 15 minutes.
- [ ] STATUS.md has no open items about IRIS compatibility.

**Not part of this bounty — InterSystems DevRel handles**

- The grafana.com organisation and signing token. The plugin ID `intersystems-iris-datasource` presumes the signing organisation is `intersystems`.
- The approved logo.
- Signing, catalog submission and the choice of signature level.

> **Note for DevRel:** Talk to the author of the existing community plugin before posting. Two near-identical IRIS plugins is a likely rejection reason in Grafana's manual review, and inviting him turns a competitor into the contributor.

### Get the IRIS source connector contribution-ready for Airbyte

*Recommended · gap #9 · M — a few weeks · Open bounty; Python and Docker experience*

**Why it matters.** Airbyte runs in more than 170,000 deployments, and an IRIS connector has only ever been an unclaimed idea on the InterSystems Ideas portal. Estuary relists Airbyte connectors, so one accepted connector shows up in two catalogs.

**Where to start.** `connectors/airbyte-source-iris` in `intersystems-community/iris-ai-examples` is an Airbyte CDK source with spec, check, discover and read; full-refresh and incremental sync; 72 offline tests; and the contribution files Airbyte expects (`metadata.yaml`, `Dockerfile`, `acceptance-test-config.yml`, docs page). It has never run against a real IRIS, and Airbyte's Docker-based acceptance tests have never run.

**What you need.** Docker, Python 3.11 and IRIS Community Edition. Everything is free.

**What to deliver**

1. Validate against live IRIS: `check` succeeding and failing; `discover` against a schema containing `%PosixTime`, stream/LOB, NUMERIC precision, composite-key and no-key tables; a full refresh; and an incremental sync that picks up new rows and resumes from saved state.
2. Make Airbyte's acceptance tests pass against IRIS Community in Docker, and run them in CI.
3. Make Airbyte's connector QA checks pass. Set the licence to MIT in both `metadata.yaml` and `pyproject.toml` — the checks accept MIT or ELv2 and require the two files to match.
4. Refresh the base-image digest in `metadata.yaml`; the current one is stale.
5. Complete the docs page: setup, supported sync modes, the type map and known limitations.
6. Hand over a branch ready for a pull request to `airbytehq/airbyte`.

**Done when**

- [ ] Acceptance tests and the live-IRIS suite are green in CI.
- [ ] Airbyte's QA checks pass.
- [ ] DevRel can run a sync from IRIS Community into a local Airbyte from the README.
- [ ] STATUS.md has no open items about IRIS compatibility.

**Not part of this bounty — InterSystems DevRel handles**

- Opening and owning the pull request to `airbytehq/airbyte`.
- The connector icon.
- Test credentials, which Airbyte stores in its own secret store.

> **Note for DevRel:** Confirm with Legal that MIT is acceptable before posting; the staged copy currently declares ELv2.

### Ship the IRIS → Microsoft Fabric Open Mirroring publisher

*Recommended · gap #5 · M — a few weeks · Open bounty; Azure and Fabric experience*

**Why it matters.** Many organisations that run IRIS are moving their analytics to Microsoft Fabric, where Snowflake and Azure Databricks can be mirrored directly and IRIS cannot. Fabric's Open Mirroring lets any application push changes into a mirrored database without Microsoft building anything. Microsoft also lists Open Mirroring partners on its own documentation page.

**Where to start.** `connectors/fabric-open-mirroring-iris` in `intersystems-community/iris-ai-examples` already writes the Open Mirroring landing-zone format — Parquet change files, `_metadata.json` and sequencing — through a crash-safe publisher with 47 offline tests. It does not yet upload to OneLake, and nothing runs it continuously.

**What you need.** A Fabric trial (60 days, Open Mirroring included; mirroring stops when the trial ends), an Azure service principal, and IRIS Community Edition. Free for the length of the trial.

**What to deliver**

1. Build the upload to OneLake through the ADLS Gen2 / Blob API with service-principal auth, keeping the existing guarantees: a retried or re-run upload must never duplicate or reorder changes.
2. Package it to run as a service, with a config file, a sync interval, logging, and resume after a restart.
3. Implement change tracking with a watermark plus soft-delete convention, and document plainly that hard deletes are only captured if the source schema follows it.
4. Confirm the type map against a live IRIS, and confirm where `_partnerEvents.json` belongs against a live Fabric tenant.
5. Run end to end in a Fabric trial: an initial snapshot, then inserts, updates and deletes, all appearing in the mirrored database and queryable through its SQL analytics endpoint. Record a short video and screenshots.

**Done when**

- [ ] DevRel can reproduce the end-to-end run in its own trial tenant from the README.
- [ ] The offline and live-IRIS suites pass in CI.
- [ ] A kill-and-restart test against real OneLake shows no duplicated or missing changes.

**Not part of this bounty — InterSystems DevRel handles**

- Contacting Microsoft about the Open Mirroring partner page.
- The separate request for native mirrored-source status.
- Any paid Fabric capacity.

> **Note for DevRel:** The bounty taker's trial clock is the real deadline — set the bounty window inside 60 days.

### Get IRIS onto Apache Superset's list of supported databases

*Quick win · gap #17 · S — days · Invite the author of `superset-iris` first*

**Why it matters.** Superset already works with IRIS through the community `superset-iris` and `sqlalchemy-iris` packages, but IRIS is missing from Superset's own list of supported databases. That list is generated from engine specs in Superset's code, so adding one upstream fixes both at once.

**Where to start.** The `superset-iris` package, and Superset's guide to engine specs (`superset/db_engine_specs/README.md`).

**What you need.** Apache Superset and IRIS Community Edition in Docker. Free.

**What to deliver**

1. Open a pull request to `apache/superset` adding an IRIS engine spec, including the `metadata` attribute that generates the docs entry, time grains, and IRIS SQL specifics.
2. Add the tests Superset's conventions require.
3. Show IRIS appearing in the locally generated docs.

**Done when**

- [ ] The pull request is open with Superset's CI green.
- [ ] IRIS appears in the generated database list.

**Not part of this bounty — InterSystems DevRel handles**

- Nothing beyond announcing the result. Superset's maintainers own the engine spec once it is merged, so this one creates almost no maintenance load.

### Assess dbt-iris against dbt's Trusted Adapter bar

*Quick win · gap #12 · S — days · Invite the `dbt-iris` maintainer first*

**Why it matters.** Trusted adapters get top billing in dbt's documentation, and dbt-iris is currently a community adapter. Before anyone commits to Trusted status — which includes keeping pace with dbt releases indefinitely — we need to know how far the adapter is from the bar.

**Where to start.** The community `dbt-iris` adapter and dbt's adapter test suite, `dbt-tests-adapter`.

**What you need.** dbt Core and IRIS Community Edition. Free.

**What to deliver**

1. Run `dbt-tests-adapter` against IRIS Community and report pass or fail for each feature.
2. Write up the gaps against the Trusted Adapter requirements, with an effort estimate for each.
3. Draft the setup and configuration pages that dbt's documentation site would host for the adapter.

**Done when**

- [ ] DevRel has a test report it can reproduce and a gap list it can price.
- [ ] Closing the gaps becomes a follow-on bounty, if DevRel commits.

**Not part of this bounty — InterSystems DevRel handles**

- Deciding whether to commit to the ongoing maintenance Trusted status requires, before applying.

## Before posting

- [ ] **Licences.** The repo has no top-level licence and 7 of the 10 staged connectors declare none, so nobody can legally build on them yet. Pick a licence for each bounty's code — Grafana is already Apache-2.0; MIT suits Airbyte and Fabric — and add the files.
- [ ] **Bounty terms.** Include a grant letting InterSystems maintain the code and submit it under its own name, plus the 30-day review-support clause. Without the grant, DevRel cannot take over maintenance.
- [ ] **Make the starting code reachable.** It currently lives on a working branch of `iris-ai-examples`, not `main`. Merge it, or extract each connector into its own repository, before the bounties link to it.
- [ ] **Talk to caretdev first.** Three of the five suggested takers are the same person, whose community packages these bounties build on. Invite rather than compete — and note that this concentrates work in one person, the very risk the research flagged.
- [ ] **Have DevRel's pieces ready.** A grafana.com organisation matching the plugin ID, the approved IRIS logo, and a named contact for Microsoft's Open Mirroring partner page — so a finished bounty doesn't sit waiting.
- [ ] **Set reward tiers.** The briefs size the work (S or M) but leave Global Masters points to you. One option: M bounties at roughly three times the S ones, with a bonus when the listing actually goes live.


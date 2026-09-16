# Publishing this connector: the real path(s), and who at InterSystems must own it

This is not one program with one form to fill out. Fivetran has **three
distinct mechanisms** that this connector could go through, with very
different bars, timelines, and current availability. Researched via
`WebSearch`/`WebFetch` in this session; `docs.intersystems.com` and
`fivetran.com` are both blocked by this environment's egress proxy, so
citations below are to pages `WebSearch` could still summarize (its
snippets, quoted directly), and to `raw.githubusercontent.com` pages that
**were** fetched in full. No account was created, nothing was submitted,
and no POST/PUT request was made anywhere, per this task's hard rules.

## The three mechanisms, from lowest to highest bar

### 1. Self-serve Connector SDK deploy -- available today, no Fivetran approval needed

Anyone with a Fivetran account (including InterSystems, or any InterSystems
customer) can `pip install fivetran-connector-sdk`, write a connector in
Python -- exactly what this directory does -- run `fivetran debug` locally,
and run `fivetran deploy` to push it straight into their own Fivetran
account's destination. This is **not** a submission to Fivetran; nothing is
reviewed, nothing is listed anywhere public, and it works the moment the
code runs. This is the mechanism this connector was built against and
validated with (`fivetran debug`; see `README.md`/`STATUS.md`).

Source: `fivetran.com/docs/connector-sdk` and
`fivetran.com/docs/connector-sdk/deploying-connectors` (per `WebSearch`
summaries -- direct fetch blocked): "Fivetran's Connector SDK allows users
to execute custom, self-written Python code within Fivetran's secure cloud
environment... Once deployed, your custom connector functions like any
native Fivetran connector -- complete with sync management, scheduling and
compute resource management."

### 2. `fivetran/community_connectors` -- open today, PR-reviewed, public catalog

Fivetran maintains a public GitHub repository,
[`fivetran/community_connectors`](https://github.com/fivetran/community_connectors)
("Fivetran Connector SDK Connectors Catalog"), containing "100+ connectors
built with the Fivetran Connector SDK." It is **open for contribution right
now** -- this is the closest thing to a currently-open "get IRIS listed
somewhere Fivetran-official" path. Full README and CONTRIBUTING.md were
fetched directly (`raw.githubusercontent.com`, not blocked):

**Process** (`CONTRIBUTING.md`):
1. Fork the repo, review the Connector SDK docs and similar existing
   connectors (a template connector and an empty project skeleton are
   provided).
2. Branch from `main`, commit, open a PR against
   `fivetran/community_connectors:main`.
3. Required files: connector code, `requirements.txt` (or
   `pyproject.toml`), a connector-level `README.md` based on the repo's
   template, and an entry in the root `README.md` describing the new
   connector.
4. **Testing requirement, verbatim**: run `fivetran debug` and `fivetran
   debug --configuration=configuration.json`, and submit "lightweight,
   sanitized proof that the connector code ran, such as a screenshot or
   short log excerpt," with credentials removed. This connector already
   has exactly that (see `STATUS.md`).
5. **Review**: one Fivetran maintainer, evaluating "minimum acceptance
   criteria, not the best possible implementation." Copilot review is
   mandatory; critical findings must be addressed, non-critical feedback is
   advisory.
6. **Acceptance criteria**: one human approval; all automated checks
   (formatting, linting, CLA) pass; Copilot review completed; validation
   evidence provided; required files present; code functional without
   material flaws.
7. **Rejection criteria**: non-functional code or connection failures;
   schema/state/data-handling errors risking data loss or corruption;
   major reliability/scalability issues; exposed credentials; security
   risks; missing required files/docs/checks. Style/formatting/speculative
   edge-case feedback does **not** block approval.
8. Community connectors get a 14-day trial period before usage counts
   toward paid Measured Addressable Replication (MAR).

Licensed MIT; maintained by Fivetran's own developers.

This connector, as it stands in this directory, already satisfies most of
requirement 3-4 above (code, `requirements.txt`, `fivetran debug` output).
What it is missing to actually open that PR: a live-IRIS-verified run
(see `STATUS.md` UNVERIFIED), and the connector-level README reshaped to
that repo's specific template (this directory's `README.md` covers the
same ground but was written for this repo's structure, not theirs).

### 3. The formal Partner-Built program -- the one this connector is NOT eligible to go through right now

This is the program that puts a connector in Fivetran's own native
connector catalog, alongside Fivetran-built connectors, typically with
a partner's logo -- the outcome the task's background (DPI-I-449, Fivetran
Support's stated "no plans") is really about. Per `WebSearch` summaries of
`fivetran.com/docs/partner-built-program` and
`fivetran.com/docs/connectors/partner-built-program`:

> "The Partner-Built program is not accepting new partners at this time."

Everything else below describes the program **as documented for existing
partners**, for completeness -- it is not currently a door InterSystems can
walk through, but it is useful to know what it demands if/when Fivetran
reopens it, or if InterSystems already has a partner relationship with
Fivetran through another channel that could ask directly:

- **What it's for**: source *and* destination connectors, built by the
  partner and run on Fivetran's infrastructure via a heavier gRPC-based
  Partner SDK (Java/Golang/Rust recommended -- a statically-linked binary,
  not the lightweight Python Connector SDK this directory uses). Proto
  files and examples: [`fivetran/fivetran_partner_sdk`](https://github.com/fivetran/fivetran_partner_sdk).
- **Process for an accepted partner**: explore the Partner SDK repo, agree
  a Partnership Agreement, build the connector. Code goes into a repo
  Fivetran can pull from (public, or private with access granted);
  Fivetran inspects it and builds the deployable executable; up to a week
  for review and deployment.
- **Release phases**: deployed to production marked "in dev," hidden from
  mutual customers, for final end-to-end testing and documentation.
  **Source connectors must be promoted to Beta within six months of
  entering Private Preview.** Private Preview usage is free; Beta and
  General Availability incur paid usage.
- **Support**: refer to the *partner's own* SLA/support documentation, not
  Fivetran's -- Fivetran does not take on first-line support for a
  partner-built connector.
- There is a **separate, unrelated "Certification Program"** (sales and
  technical certification, self-paced, online) for partner *staff*, not
  for a connector's code -- do not conflate the two.

There is also a **"By Request" program**
(`fivetran.com/docs/by-request-program`), which is a different thing
again: an *existing Fivetran customer* submits a "Lite Connector Request"
form for a connector they personally want, Fivetran builds it, and it is
added to Fivetran's catalog. Per `WebSearch`: "Fivetran is limiting this
program to their users... suitable for Fivetran users looking for a SaaS
application connector... or a connector for a service that uses HTTP
APIs." IRIS is a database with a DB-API driver, not a SaaS/HTTP-API
service, so this program is a poor fit even setting aside that it, too,
is not something InterSystems can initiate on its own (a customer has to
ask).

## Recommendation, plainly

Given #3 is closed, the realistic path to "IRIS is visibly present in
Fivetran's ecosystem" today is **#1 (deploy it, use it, put it in
InterSystems' own hands and docs) plus #2 (open a PR to
`community_connectors` once it's been verified against a live IRIS
instance)**. Neither requires Fivetran's permission. Revisit #3
periodically (the program's acceptance status is Fivetran's own
statement, not a permanent policy) and if InterSystems already has any
existing partner/ISV relationship with Fivetran through another channel
(sales, alliances), that relationship -- not a cold outbound request -- is
the only realistic way back into a closed partner program.

## Who at InterSystems must own it

This connector's code can live anywhere (this directory, or a dedicated
repo per `../README.md`'s placement caveat), but three things need an
owner who is not "whoever wrote the code":

1. **A live IRIS instance to verify against**, and sign-off that the
   `db.py` real-connection path, the `INFORMATION_SCHEMA` query shapes, and
   the `POSIXTIME`/stream-column assumptions in `README.md`/`STATUS.md`
   actually hold. This is an IRIS SQL/product-engineering owner, not a
   partnerships one.
2. **A Fivetran account to run `fivetran deploy` against and open the
   `community_connectors` PR from** -- ideally an InterSystems corporate
   Fivetran account, not an individual's, since the PR's authorship and
   any resulting support questions will be attributed to whoever's account
   and GitHub identity did it.
3. **An ISC Alliances/partnerships contact for Fivetran**, to (a) ask
   directly whether the Partner-Built program's "not accepting new
   partners" status has an exception path for a strategic data-platform
   partner, and (b) be the point of contact `community_connectors`'
   Fivetran-maintainer reviewer reaches if they have questions about an
   `INTERSYSTEMS`-labeled connector showing up in their PR queue -- a
   community PR from an unrecognized individual account reads very
   differently to a reviewer than one that's visibly from InterSystems.

None of this can be done from inside this task: it requires a live IRIS
instance, a Fivetran account, and human organizational authority this
session does not have and was explicitly told not to create or exercise.

## Sources

- [`github.com/fivetran/community_connectors`](https://github.com/fivetran/community_connectors) -- README and CONTRIBUTING.md fetched in full via `raw.githubusercontent.com`.
- [`github.com/fivetran/fivetran_partner_sdk`](https://github.com/fivetran/fivetran_partner_sdk) -- Partner SDK repo (via `WebSearch`).
- `fivetran.com/docs/partner-built-program` / `fivetran.com/docs/connectors/partner-built-program` -- Partner-Built program status and process (via `WebSearch` summary; direct fetch blocked by this environment's egress proxy).
- `fivetran.com/docs/by-request-program` -- By Request program (via `WebSearch` summary).
- `fivetran.com/docs/connector-sdk`, `fivetran.com/docs/connector-sdk/deploying-connectors` -- self-serve Connector SDK deployment (via `WebSearch` summary).

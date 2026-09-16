# Publishing tableau-iris to the Tableau Exchange

This document is research, not an announcement — nothing in this
connector has been submitted, signed, or published anywhere. See
`STATUS.md` and `../README.md`'s "Verification ceiling" for what this
session could and couldn't do. Every claim below is cited; anything this
session could not confirm is marked as such.

## The precedent this closes a gap against

InterSystems already ships a **certified** InterSystems IRIS connector
**built into Power BI Desktop** — announced April 2019, and per
`docs.intersystems.com`'s own Power BI integration page (via WebSearch,
2026-09-16), it remains built in today (the underlying product was
renamed the "InterSystems Health Insight Connector" after exiting beta
in July 2024, but the "built into Power BI Desktop, certified by
InterSystems" facts haven't changed).
[Sources: intersystems.com press release](https://www.intersystems.com/news/intersystems-releases-certified-intersystems-iris-data-platform-connector-for-microsoft-power-bi/),
[docs.intersystems.com APOWER](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=APOWER).

Tableau has no equivalent: IRIS is reachable only through the generic
"Other Databases (ODBC/JDBC)" connector, with no Tableau Exchange
listing and no named connector. That asymmetry is gap #7 in
`../../research/ecosystem-connector-gaps.md`, and this connector is a
starting point for closing it — not a finished submission.

## What Tableau Exchange actually requires (confirmed via WebSearch against tableau.github.io, 2026-09-16)

Direct fetches to `tableau.github.io` are blocked by this session's
egress proxy (confirmed: `EGRESS_BLOCKED` from the `WebFetch` tool), so
everything below comes from WebSearch result snippets that quote or
summarize `tableau.github.io/connector-plugin-sdk/docs/gallery-submission`
and `.../docs/package-sign`, not a full read of those pages. Re-read them
directly before actually submitting anything.

### Signing

- The `.taco` must be **signed with a code-signing certificate issued by
  a certificate authority trusted by the Java environment doing the
  signing** — a self-signed certificate is not sufficient.
- The signature must carry a **timestamp valid for at least five years**
  from signing.
- For a **partner connector** (built by the vendor, i.e. InterSystems,
  rather than by Tableau or a customer), Tableau's own submission
  checklist additionally requires that "the signer is the organization
  that built the connector."
- Signing is performed with the JDK via
  `connector-packager` (see `README.md`'s Build section), driven by four
  properties: `taco.signing.keystore` (path to the `.jks` keystore),
  `taco.signing.alias`, `taco.signing.storepass`, `taco.signing.keypass`.
- None of this happened in this session — there is no keystore, no code-
  signing certificate, and no signed `.taco` anywhere in this
  connector's deliverables. See STATUS.md HUMAN ACTIONS REQUIRED.

### Testing requirements for submission

- Tableau's own automated harness is **TDVT** (Tableau Datasource
  Verification Tool), part of the same `connector-plugin-sdk` repo this
  connector's schemas came from. TDVT drives `tabquerytool.exe` — a
  **Windows-only command-line tool that requires a real Tableau
  installation** — against `.tds` files and logical/expression query
  test suites.
- Per Tableau's submission guide, certain categories of change (their
  "List B") require **full TDVT results**; connectors that also touch
  "List C" changes require **TDVT and full manual test results**. A
  brand-new connector for a database with no existing Tableau dialect —
  this one — falls squarely into "needs full TDVT," not the lighter
  path.
- TDVT cannot run in this environment: no Windows, no Tableau
  installation, no `tabquerytool.exe`. This is a hard blocker, not a
  scope choice — see STATUS.md.
- Submissions that add vendor-defined fields must document each one:
  what it is, a sample input, and confirmation it can never contain PII.
  This connector adds none beyond Tableau's own canonical field set
  (server/port/dbname/username/password/ssl), so that requirement is
  currently moot — it would only bite if a future revision adds
  IRIS-specific vendor fields (e.g. an explicit `driverLocator` override
  or a Kerberos SPN).

### Security review

Tableau performs its own security review as part of the connector
review process, and can pull an already-published connector from the
Exchange if a vulnerability is later found in it. Nothing about that
review process happened here — the `security-review` skill available in
this environment reviews source code diffs, not a packaged, signed
`.taco`, and no such artifact exists yet to review.

### Forbidden changes

Once published, **the connector `class` attribute in `manifest.xml` can
never change** — Tableau's guide calls this "essentially a new
connector" and says it will never be approved. `manifest.xml` in this
connector uses `class='iris_jdbc'`; if InterSystems ever ships this
connector, that string effectively becomes permanent API surface the
moment the first version is accepted, so it's worth deciding
deliberately (with input from whoever owns the InterSystems partner
relationship with Tableau — see "Who owns this" below) rather than
treating it as an implementation detail.

## Certification / verification tiers

This session could not confirm Tableau's current tier names and exact
criteria (e.g. whether there's still a distinct "Tableau Supported" vs.
"Verified" vs. partner-built badge, and what each requires beyond
signing + TDVT) against a primary source — WebSearch snippets on this
point were thin and Tableau's docs site itself is blocked for direct
fetch in this session. What the `connector-plugin-sdk` repository's own
`README.md` (cloned and read directly in this session, not via search)
does confirm: it displays a
`![Tableau Supported](https://img.shields.io/badge/Support%20Level-Tableau%20Supported-53bd92.svg)`
badge on itself, and states plainly: *"Not necessarily [will Tableau
include your connector] — we plan to include connectors on a case by
case basis... we have included a few partner built connectors, and we
are looking at providing a way to include third-party connectors in the
future through a more formal validation program... get in touch with
our Technology Partner team."* That "get in touch with our Technology
Partner team" (`tableau.com/partners/become`) is the actual first step,
not a self-service submission form — flag this as **UNVERIFIED**: this
session does not know the current, complete tier structure and cannot
be treated as authoritative on it. Confirm directly against
`tableau.github.io/connector-plugin-sdk/docs/gallery-submission` before
representing any tier to a partner-relations contact.

## Testing matrix (Desktop / Server / Cloud)

None of this was executed. This is the matrix a human tester needs to
run before any submission, derived from what TDVT and Tableau's
packaging docs describe testing against:

| Surface | What to verify | Can this session do it? |
| --- | --- | --- |
| Tableau Desktop (Windows) | `.taco` drops into `My Tableau Repository/Connectors`, connection dialog renders, connects, browses namespace/schema, builds a basic worksheet | No — no Windows, no Desktop install |
| Tableau Desktop (Mac) | Same, plus the Mac-specific `.taco` signature-verification bug noted in the SDK's own `README.md` Known Issues section (worked around pre-2019.4.1 with `-DDisableVerifyConnectorPluginSignature=true`, fixed since) | No — no Mac, no Desktop install |
| Tableau Server | `.taco` deployed to the server's connector directory, admin-level install permissions, live-query and extract-refresh workbooks published from Desktop | No — no Server install |
| Tableau Cloud | Cloud has tighter constraints on custom connectors than Server (generally requires a Tableau Bridge client for on-prem sources like IRIS, and Cloud's own connector allowlist policy) — this session found no concrete IRIS+Tableau Cloud guidance to cite and flags this whole row as needing direct confirmation from Tableau's Cloud documentation | No — no Cloud tenant, and the specifics are unconfirmed even on paper |
| TDVT full suite | Logical-query and expression-query test files against a live IRIS instance, run via `tabquerytool.exe` | No — Windows-only tool, needs Tableau + live IRIS |
| Manual test pass | Whatever Tableau's submission guide's "List C" manual checklist actually enumerates | No — this session never obtained that checklist's full text |

## Who at InterSystems should own this

This session has no access to InterSystems' internal org chart and does
not know who owns Tableau specifically. What's inferable from public
precedent: the Power BI connector was announced as an InterSystems
product release (intersystems.com press release, not a community post),
which suggests a **product/partnerships team** drove that relationship,
likely the same group that would own a Tableau Technology Partner
relationship (`tableau.com/partners/become`) and any future Exchange
submission. `../../CLAUDE.md`'s container/example ownership table names
individual examples' owners but says nothing about who owns
ecosystem-connector strategy — that's a gap in this repo's own
documentation, not something this task can resolve. **Flag for a human
at InterSystems**: identify the actual owner (likely someone adjacent to
whoever ran the Power BI certification) before doing anything with this
connector beyond keeping it as a reference implementation.

## Suggested path from here (not started)

1. A human confirms the current Tableau Exchange submission and
   certification-tier requirements directly against
   `tableau.github.io/connector-plugin-sdk/docs/gallery-submission` (this
   session's summary above is WebSearch-derived, not a primary read).
2. Stand up a real IRIS instance and Tableau Desktop, and manually
   exercise every capability flag and dialect formula in
   `connector/manifest.xml` / `connector/dialect.tdd` — everything in
   `STATUS.md`'s UNVERIFIED section needs this before it can move to
   VERIFIED.
3. Run the full TDVT suite once step 2 passes manually.
4. Obtain a code-signing certificate and package/sign per `README.md`'s
   Build section.
5. Reach out via `tableau.com/partners/become` (Technology Partner
   program) — per the SDK's own README, this is the actual gate for
   getting a partner connector included, not a self-service upload.

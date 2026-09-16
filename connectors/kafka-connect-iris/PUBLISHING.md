# Publishing to Confluent Hub — requirements

This is a research/requirements document, not a submission. **Nothing in
this session created a Confluent account, submitted anything to Confluent,
or contacted Confluent in any way.** Everything below was assembled from
public documentation search results; direct fetches of `docs.confluent.io`
and `www.confluent.io` were blocked by this environment's network egress
policy, so citations below are to the pages found, with the caveat that
their content came through search-result snippets rather than a full page
read. **Human action: re-verify every field/requirement below directly
against the live docs before acting on this document** (see STATUS.md).

## 1. What "publishing to Confluent Hub" actually requires

Confluent Hub distributes connectors as a **component archive**: a zip
with a specific internal layout plus a `manifest.json` describing the
component. This is a packaging format Confluent's tooling validates, not
a moderated app-store listing you upload once for review-and-approve --
but see section 3 for the separate *Verified Integration* program, which
does have a review step.

Source: [Confluent Hub component archive specification](https://docs.confluent.io/kafka-connectors/self-managed/confluent-hub/component-archive.html)

### 1a. Component archive layout

```
<archive-root>/
├── manifest.json      Required. Metadata shown on the Hub listing.
├── assets/            Logos/icons used on the Hub listing.
├── doc/                README, LICENSE, and other human-readable docs.
├── etc/                Sample/default connector .properties files.
└── lib/                All jars needed to run the component (the connector's
                        own classes plus every non-"provided" runtime
                        dependency -- for this connector, that means the
                        intersystems-jdbc jar must be in here alongside
                        kafka-connect-iris.jar; connect-api itself must NOT
                        be, since the Connect worker supplies it).
```

The `confluent-hub-client` CLI validates that an archive has this
structure (manifest present, in the right place) before it can be
installed with `confluent-hub install`.

Source: [Confluent Hub Client docs](https://docs.confluent.io/platform/7.5/connect/confluent-hub/client.html)

### 1b. `manifest.json`

Confirmed-real fields (from search-result snippets of Confluent's own
example manifests -- **the authoritative field list is the "Component
Manifest" doc under the Component Archive Specification page above, and
should be read in full before writing a real manifest**):

- `component_types` — e.g. `["source"]` or `["sink"]`
- `name`, `title`, `version`, `description`, `owner` — identity/branding
  fields; `owner` in Confluent's own examples is a Confluent-style
  identifier block (name + a hub-assigned username), which for an
  InterSystems-owned listing would need to be InterSystems' own
  registered Hub owner account, not an individual's.
- `documentation_url`, `license` — links/licensing metadata.
- `features` — a block including things like
  `confluent_control_center_integration`, `delivery_guarantee`,
  `kafka_connect_api`, `single_message_transforms`, `supported_encodings`.
- `docker_image` — optional, for a connector also shipped as a container
  image (tag/name/namespace/registry).

Confluent also publishes a **Maven plugin**
(`kafka-connect-maven-plugin`) that auto-generates the component archive
--including `manifest.json`, `etc/`, `doc/`, and `lib/` -- from a Maven
build. This project's `pom.xml` does **not** use it: the plugin is
distributed through Confluent's own Maven repository, which was not
reachable/attempted in this environment's proxy-scoped build (Maven
Central only), and pulling in a build-time dependency on a third-party
plugin without being able to verify it resolves would have been a worse
outcome than documenting the requirement here.

Source: [kafka-connect-maven-plugin docs](https://docs.confluent.io/platform/current/connect/kafka-connect-maven-plugin/site/kafka-connect-mojo.html);
[How to Contribute a Kafka Connector on Confluent Hub (Confluent blog)](https://www.confluent.io/blog/how-to-share-kafka-connectors-on-confluent-hub/)

### 1c. Naming/versioning

The archive's own filename and the `version` field should track this
project's Maven `${project.version}` (already wired to `Version.get()` at
runtime -- see `Version.java`) so the Hub listing's reported version
matches what `Connector.version()` actually reports to a running worker.

## 2. Component packaging this project has NOT built

To be explicit about the gap between "a Maven project that compiles and
tests pass" (this directory, today) and "a thing installable via
`confluent-hub install`":

- No `manifest.json` exists here.
- No `lib/`, `etc/`, `doc/`, `assets/` layout has been assembled.
- No shaded/uber-jar or dependency-bundling step exists in `pom.xml` --
  `mvn package` produces a plain jar containing only this project's own
  classes (verified; see STATUS.md), not `intersystems-jdbc.jar`'s
  contents or anything else the `lib/` folder would need.

This is deliberate scope discipline, not an oversight: assembling that
layout by hand without ever validating it against the real
`confluent-hub-client` validator (which was not attempted here — see
Section 4) would produce something that *looks* Hub-shaped without any
assurance it passes Hub validation, which is arguably worse than clearly
stating it wasn't attempted.

## 3. The verification/partner tiers

Confluent's own connector-quality program has changed shape over time and
the search results returned mixed signals on its *current* state, which
is exactly why this needs direct re-verification before InterSystems
relies on it:

- Historically, two tiers existed: **Gold** (tightest integration with
  Confluent Platform; every "should-have" criterion met) and **Standard**
  (every "must-have" criterion met, i.e. functional/practical).
- More recent search results describe Confluent now accepting only a
  single tier, **Verified Integration** (described as "formerly Gold
  level").
- Verification, in both the old and new framing, requires the submitting
  organization to be a **registered Confluent Partner** — this is an
  organizational relationship, not something a single connector submission
  can satisfy on its own. Verification also checks the integration
  functions correctly across applicable Confluent deployment options,
  has adequate documentation, has appropriate licensing, and follows Kafka
  Connect / Schema Registry best practices.

Sources: [A Guide to the Confluent Verified Integrations Program (Confluent blog)](https://www.confluent.io/blog/guide-to-confluent-verified-integrations-program/);
[Confluent Verified Integration FAQs](https://www.confluent.io/confluent-verified-integration-faqs/);
[Verified Integration Program Verification Guide: Sources and Sinks (PDF)](https://assets.confluent.io/m/28c7ffcc359a13c0/original/20200325-VIP_Connect-Verification_Guide.pdf);
[Confluent Partner Program FAQ (PDF)](https://www.confluent.io/wp-content/uploads/Confluent-Partner-Program-FAQ-032018.pdf)

**Unlisted (unverified) submission to the Hub catalog itself may be
possible without partner status** — several community connectors appear
on Confluent Hub without a "Verified" badge — but this document did not
find a citable, current confirmation of that path's exact requirements,
and it should be confirmed directly with Confluent before InterSystems
plans around it.

## 4. Who at InterSystems should own this

This session found **no public record of an existing InterSystems ⟷
Confluent technology partnership** (search results returned InterSystems'
own [Technology Alliance Partners program](https://www.intersystems.com/partners/technology-alliance-partners/)
and Confluent's [general partner-finder page](https://www.confluent.io/partner/),
but no announcement or listing connecting the two). That means, most
likely, **becoming a registered Confluent Partner is itself a prerequisite
step**, not a formality, and is an organizational/business decision, not
an engineering one.

Recommended internal routing (this is this document's own inference from
the above, not a confirmed fact — flagged as such, and needs a named
owner from InterSystems, not from this session):

1. **InterSystems Alliance/Partnerships team** (the group that runs the
   Technology Alliance Partners program) — to evaluate and, if desired,
   initiate a Confluent partner relationship.
2. **Interoperability / Data Platform product management** — to own the
   long-term connector itself (config surface, IRIS-version compatibility,
   deprecation policy) the way `sqlalchemy-iris`, `dbt-iris`, etc. are
   currently owned by an external community maintainer rather than
   InterSystems itself (see `../../research/ecosystem-connector-gaps.md`'s
   "single-maintainer risk" framing) — this connector should not become a
   fifth entry on that same list.
3. **Developer Relations / Developer Community** — the existing publisher
   of record for `confluent-kafka-iris` on Open Exchange
   (https://openexchange.intersystems.com/package/confluent-kafka-iris),
   who may already have relevant contacts or prior art to reconcile with
   this connector rather than duplicate.

## 5. Concrete next steps (human-executed, outside this session's scope)

1. Confirm current Confluent Hub submission mechanics directly against
   `docs.confluent.io` (this session's network egress could not reach that
   domain — see STATUS.md) and against `www.confluent.io` for the current
   state of the Verified Integration program (also blocked here).
2. Decide unlisted-Hub-submission vs. full-partner-verification as the
   target, since they have very different lead times and owners (Section 3).
3. If pursuing partner status, route through InterSystems
   Alliance/Partnerships (Section 4) before any code-level packaging work.
4. Only once 1–3 are resolved: add a Confluent Hub packaging step to this
   project's `pom.xml` (via `kafka-connect-maven-plugin` or an equivalent
   `maven-assembly-plugin` descriptor reproducing the `lib/`/`etc/`/`doc/`/
   `assets/`/`manifest.json` layout in Section 1a) and validate the result
   with the real `confluent-hub-client`, which this session did not have
   available to test against.

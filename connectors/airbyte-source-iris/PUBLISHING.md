# Publishing source-iris to airbytehq/airbyte

This is the real contribution path, as documented by Airbyte, for turning this staged
connector into a listed entry in Airbyte's connector registry. Nothing in this section
was executed — no PR was opened, no account was created, no image was published (see
`STATUS.md` and the repo-wide hard rule against submitting to any vendor). This is a
map of the path, cited from Airbyte's own docs, for whoever at InterSystems picks this
up.

## 1. Where the code has to live

Airbyte connectors are contributed as a subdirectory of the **monorepo**,
[`airbytehq/airbyte`](https://github.com/airbytehq/airbyte), at
`airbyte-integrations/connectors/source-iris/`, via a fork + pull request — per
["Contribute a New Connector"](https://docs.airbyte.com/contributing-to-airbyte/submit-new-connector).
That doc's own guidance (paraphrased from search results fetched while building this,
not hand-verified page-by-page): don't open the PR from your fork's default branch,
since Airbyte maintainers push formatting fixes directly to contributor branches, and
CI (`airbyte-ci`) runs unit/integration/acceptance tests automatically on the PR.
There is also a Connector Builder UI path ("Publish → Contribute to Marketplace",
which opens the PR for you given a GitHub personal access token with `repo` scope),
but that's for manifest-only/low-code connectors built in the UI — this connector is
hand-written Python, so the fork+PR path is the applicable one.

This staged copy at `connectors/airbyte-source-iris/` in `iris-ai-examples` is laid
out to make that move mechanical: `source_iris/`, `unit_tests/`, `metadata.yaml`,
`acceptance-test-config.yml`, `docs/iris.md`, and `pyproject.toml` would move as-is
into that path; `README.md`/`PUBLISHING.md`/`STATUS.md` are specific to staging in
this repo and would not move over verbatim.

## 2. Build convention — confirmed by direct inspection, not by running airbyte-ci

Fetched several **current** (2026) Python-CDK database-source connectors' directories
directly from `airbytehq/airbyte`'s `master` branch to confirm the current layout
(cited file-by-file in `README.md`/this file/`source_iris/*.py` docstrings). The
finding: **none of them ship a `Dockerfile`** (`source-firebolt`, `source-google-sheets`
checked directly; `source-pokeapi` too, though that one's manifest-only). Instead,
`metadata.yaml`'s `data.connectorBuildOptions.baseImage` names a base image (for
Python: `airbyte/python-connector-base`), and Airbyte's own `airbyte-ci` build
tooling ([`airbyte-ci/connectors/pipelines/README.md`](https://github.com/airbytehq/airbyte/blob/master/airbyte-ci/connectors/pipelines/README.md))
builds the final image from that base plus the connector's `pyproject.toml`/source at
PR/publish time — no repo-local Dockerfile needed or wanted.

This is a real, fairly recent convention shift from the older per-connector
`Dockerfile` pattern (which is why the task that produced this repo asked for one
explicitly, and got one — see this connector's `Dockerfile` — for manual/local
builds, clearly commented as non-canonical for actual contribution).

**Not verified**: `airbyte-ci` itself was not run (it requires cloning the full
monorepo and its own toolchain; not attempted here — see STATUS.md). The claim above
about how it builds Python connectors is inferred from the `pipelines/README.md` and
from the *absence* of Dockerfiles in real merged connectors, not from watching
`airbyte-ci` build this specific connector.

## 3. Required files — confirmed against real, current connector directories

Fetched directly from `airbytehq/airbyte` (raw file contents, not the docs page,
since `docs.airbyte.com` itself is not reachable from this environment — see
STATUS.md):

| File | Confirmed by |
| --- | --- |
| `metadata.yaml` | `source-firebolt/metadata.yaml`, `source-pokeapi/metadata.yaml`, `source-google-sheets/metadata.yaml`, `source-tidb/metadata.yaml` |
| `acceptance-test-config.yml` | `source-firebolt/acceptance-test-config.yml`, `source-pokeapi/acceptance-test-config.yml`, `source-google-sheets/acceptance-test-config.yml` |
| `pyproject.toml` (poetry, `[tool.poetry.scripts]` entrypoint) | `source-firebolt/pyproject.toml` |
| `icon.svg` (referenced from `metadata.yaml`'s `icon:` field) | every metadata.yaml above references one |
| a docs page at `docs/integrations/sources/<name>.md` | referenced by every `metadata.yaml`'s `documentationUrl` |
| **no** `Dockerfile` for Python-CDK connectors | absence confirmed directly (404 fetching one) for `source-firebolt`, `source-google-sheets` |

This connector ships all of the above (this repo's `Dockerfile` is the one addition,
explicitly marked non-canonical — see #2).

## 4. Certification tiers

Per [Airbyte's connector support levels doc](https://docs.airbyte.com/integrations/connector-support-levels)
(fetched via search, page itself not directly reachable — see STATUS.md) and the
["Introducing Certified & Community Connectors"](https://airbyte.com/blog/introducing-certified-community-connectors)
blog post:

- **Community** (a.k.a. "Marketplace"): maintained by the community, not covered by
  Airbyte's own support SLAs, may have breaking changes with no notice, should be
  tested by whoever runs it before production use. This is where a brand-new
  connector lands. `metadata.yaml`'s `data.supportLevel: community` (set in this repo)
  reflects that.
- **Certified**: undergoes more rigorous, more consistent testing/updates; Airbyte's
  bar for promoting a community connector to certified is not something this
  research pinned down precisely (would need Airbyte's own internal criteria, not
  published in the pages fetched here) — flagged as a gap for whoever pursues this,
  not asserted as known.
- **Enterprise**: Airbyte-hosted, SLA-backed connectors for Enterprise customers
  (e.g. Oracle, Workday per the docs). Not a realistic near-term target for a new
  community-contributed connector.

## 5. QA checks

Per the ["Airbyte connectors QA checks"](https://docs.airbyte.com/community/contributing-to-airbyte/resources/qa-checks)
doc (title/existence confirmed via GitHub code search of the docs source tree in this
session — `docs/community/contributing-to-airbyte/resources/qa-checks.md` — content
not fetched directly since `docs.airbyte.com` is unreachable here): QA checks are
**static** checks — they validate `metadata.yaml` correctness, docs presence, and
packaging shape, without executing any connector code. They run automatically in CI on
a contribution PR. This connector's `metadata.yaml`/`acceptance-test-config.yml`/docs
page were hand-built to that shape (cited above) but **have not been run through
Airbyte's actual QA check tooling**, which lives inside the monorepo's CI/`airbyte-ci`
and was not run here.

## 6. What actually gets it into the registry

The connector registry (what powers Airbyte Cloud/OSS's connector picker) is built
from every connector's `metadata.yaml` across the monorepo. Merging the contribution
PR is what gets it registered; per the search-result summary of the contribution
guide, CI runs unit/integration/acceptance tests automatically on the PR and "passing
tests are required to merge," after which a maintainer/community reviewer approves and
merges it — none of that was performed here (see hard rule: no PRs, no submissions).

## 7. Who at InterSystems should own this

This repo (`iris-ai-examples`) is AI Hub demo/reference material per its own
`CLAUDE.md`/`AGENTS.md`, not a connector's permanent home — and per
`connectors/README.md`'s "Placement caveat," this whole `connectors/` tree is staged
work whose final home is a maintainers' decision, not something decided here.
Concretely, before any contribution PR is opened, InterSystems needs a human to:

1. **Own the fork+PR relationship with Airbyte** — an InterSystems (or community)
   GitHub identity that opens, iterates on, and maintains the PR/connector long-term
   (community connectors "may experience breaking changes with no notice" and are not
   under Airbyte's SLA, so *someone* has to be the de facto maintainer even though
   Airbyte itself won't be).
2. **Decide the license** — contributing into `airbytehq/airbyte` licenses the code
   ELv2 by Airbyte's own convention (every fetched connector's `metadata.yaml` in
   this session says `license: ELv2`, including community ones like `source-tidb`).
   `pyproject.toml`/`metadata.yaml` here already say `ELv2` to match that target, but
   an InterSystems legal/OSS-program decision is needed before anything is actually
   published under that license, since this staged copy currently lives inside
   `iris-ai-examples` under whatever license governs that repo as a whole.
3. **Provide (or provision) a real IRIS instance and real credentials** for Airbyte's
   CI to run acceptance/integration tests against, stored in Airbyte's GSM-backed
   testing secret store (`connectorTestSuitesOptions.testSecrets` in `metadata.yaml`
   already names the expected secret, `SECRET_SOURCE-IRIS_CREDS`, matching the shape
   every other connector's metadata.yaml uses) — no such instance exists in this
   environment.
4. **Confirm the `%PosixTime`/stream-LOB assumptions in README.md/docs/iris.md**
   against a live IRIS instance** before anyone represents this connector's type
   handling as verified rather than "should work per documentation." See STATUS.md.
5. **Get InterSystems' own brand/marketing sign-off on an icon** — `icon.svg` here is
   a generic placeholder mark, explicitly not InterSystems' trademarked logo (see the
   file's own comment).

None of the above is a decision this session is positioned to make; it is surfaced
here, not resolved.

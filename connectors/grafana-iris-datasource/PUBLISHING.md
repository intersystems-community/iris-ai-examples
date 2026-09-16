# Publishing to the Grafana plugin catalog

This is a desk-research summary of what submitting `intersystems-iris-datasource` to
the official Grafana plugin catalog actually requires. `grafana.com` itself was
unreachable from this environment (blocked by the network egress proxy — see
STATUS.md), so everything below is sourced from Grafana's own `plugin-tools` /
`grafana-plugin-repository` GitHub repos, the `@grafana/sign-plugin` npm package
page, and the Grafana Labs community forums, surfaced through search rather than a
direct fetch of `grafana.com/developers/plugin-tools`. Re-verify against
`https://grafana.com/developers/plugin-tools/publish-a-plugin/` before actually
submitting — plugin tooling and policy change often enough that this should be
treated as a map, not the territory.

## 1. plugin.json fields the catalog checks

`src/plugin.json` in this plugin already sets these; listed here so a reviewer can
diff future changes against what the catalog expects:

| Field | Requirement |
| --- | --- |
| `id` | Must be unique across the catalog, conventionally `<org-slug>-<name>-datasource`. This plugin uses `intersystems-iris-datasource` — verify `intersystems` is the org slug InterSystems will actually publish under (see §5). |
| `type` | `"datasource"`. |
| `name` | Human-readable display name (`"InterSystems IRIS"`). |
| `info.version` / `info.updated` | Injected at build time from `%VERSION%` / `%TODAY%` placeholders — the webpack config already does this; do not hand-edit these into `src/plugin.json`. |
| `info.logos.small` / `info.logos.large` | Both required; this plugin currently ships a generic placeholder icon (`src/img/logo.svg`) — **replace with an approved InterSystems/IRIS logo before submission** (see §6). |
| `info.author`, `info.description`, `info.keywords`, `info.links` | Present; `description` and `keywords` should be reviewed by InterSystems marketing before submission, not just left as this session wrote them. |
| `info.screenshots` | Currently empty. The catalog listing strongly benefits from screenshots (config editor, query editor, a real dashboard) — none exist because there is no running IRIS or Grafana instance in this environment to screenshot against. |
| `dependencies.grafanaDependency` | Minimum Grafana version the plugin supports; set conservatively (`>=10.4.0`) here and should be tightened once real compatibility testing (§ UNVERIFIED in STATUS.md) has happened. |
| `backend` / `executable` | `true` / `"gpx_iris_datasource"`. The backend binary must be built for every OS/arch Grafana ships plugins for and named `gpx_iris_datasource_<os>_<arch>[.exe]` — this session verified `go build` cross-compiles cleanly for `linux_amd64`, `darwin_arm64`, and `windows_amd64` (see STATUS.md), but the full required matrix (at minimum `linux_amd64`, `linux_arm64`, `darwin_amd64`, `darwin_arm64`, `windows_amd64`) has not all been produced or smoke-tested. |

## 2. Required repo-level artifacts

- **README.md** — this plugin has one; the catalog page renders it, so before
  submission add real screenshots and a short GIF/video if possible (not done here —
  no Grafana UI was ever running).
- **CHANGELOG.md** — present, currently a single unreleased entry. Grafana's build
  tooling can auto-generate this from GitHub releases going forward.
- **LICENSE** — Apache-2.0, included.
- A **GitHub release** with the signed, packaged plugin as a release asset (a `.zip`
  of `dist/` plus its checksum). This plugin has never been packaged or signed — see
  §3 and §4.

## 3. Building the release artifact

1. `npm run build` (frontend) — verified in this session, produces `dist/module.js`
   + copies `plugin.json`, `README.md`, `CHANGELOG.md`, `LICENSE`, `img/logo.svg`
   into `dist/`.
2. Cross-compile the backend for every target and drop the binaries into `dist/`
   next to the frontend assets, named `gpx_iris_datasource_<os>_<arch>`, e.g.:
   ```bash
   GOOS=linux   GOARCH=amd64 go build -o dist/gpx_iris_datasource_linux_amd64   .
   GOOS=linux   GOARCH=arm64 go build -o dist/gpx_iris_datasource_linux_arm64   .
   GOOS=darwin  GOARCH=amd64 go build -o dist/gpx_iris_datasource_darwin_amd64  .
   GOOS=darwin  GOARCH=arm64 go build -o dist/gpx_iris_datasource_darwin_arm64  .
   GOOS=windows GOARCH=amd64 go build -o dist/gpx_iris_datasource_windows_amd64.exe .
   ```
3. Zip `dist/` and compute its checksum for the release asset.

## 4. Signing

- Every plugin, public or private, must be cryptographically signed before Grafana
  will load it (enforced since Grafana 7.0).
- Signing is done with the `@grafana/sign-plugin` CLI (`npx @grafana/sign-plugin`),
  which writes a `MANIFEST.txt` into `dist/`.
- **Private** plugins (installed only inside one organization's own Grafana
  instances) are signed by passing `--rootUrls` naming those instances' URLs — no
  Grafana review is required for this path.
- **Public catalog** plugins are signed only *after* the Grafana team has reviewed
  and approved the submission (§5) — you do not, and cannot, self-assign a public
  signature level. Signing then uses a **Grafana Access Policy Token**
  (`GRAFANA_ACCESS_POLICY_TOKEN`; the older `GRAFANA_API_KEY` is deprecated) rather
  than `--rootUrls`.
- **Signature levels** for catalog plugins are, from most to least restrictive on
  who may publish under them:
  - **Community** — the default level most third-party and vendor plugins get.
  - **Commercial** — for plugins tied to a paid product/support offering; requires
    a Grafana partnership/commercial agreement, not just a code review.
  - (Grafana-internal "Core"/"Grafana Labs" levels are not available to an external
    publisher like InterSystems.)
  - Which level a submission gets is decided by the Grafana review team based on
    the author and the plugin's relationship to a commercial product — this is a
    human/business decision on Grafana's side, not something this plugin's code can
    determine.

None of this — building the release zip, obtaining an access policy token, or
running the signer — was attempted in this session. There is no Grafana Cloud/access
policy account available here, and doing so would mean registering with a
third-party service, which is explicitly out of scope for this task.

## 5. Submission and review process

1. Push the plugin to a public GitHub repository (this plugin currently lives inside
   `iris-ai-examples`, which is explicitly staged-for-extraction, not the final home
   — see `../README.md`'s placement caveat).
2. Cut a GitHub release containing the signed, packaged `dist/` zip and its checksum.
3. Submit the plugin through Grafana's plugin submission form, supplying the release
   zip URL and its checksum.
4. Grafana runs an automated + manual review on every submission (new plugin or
   update). Known reasons a submission is rejected, per Grafana's own published
   criteria: forking an existing plugin without adding real value, duplicating an
   existing catalog plugin, embedding multiple plugins in one package, relying on an
   environment that limits where it can be deployed, or being a niche use case of
   limited value to the broader community. **This plugin should explicitly address
   the "duplication" criterion in its submission notes**, since
   `caretdev/grafana-intersystems-datasource` already exists — unpublished, but
   publicly visible on GitHub — as a Go/xDBC IRIS datasource plugin with SAM metrics
   support. The submission should either supersede/coordinate with that project
   (ideally with caretdev's involvement or blessing) or clearly differentiate on
   transport (REST/SQL vs. xDBC) and maintainer commitment; reviewers finding a
   near-duplicate unpublished project during review is a predictable rejection risk
   otherwise.
5. On approval, Grafana assigns a signature level (§4) and the plugin appears in the
   catalog.
6. There is no published fixed SLA for review turnaround in the sources available
   here; treat "weeks" as a planning assumption, not a documented commitment.

## 6. What an InterSystems publisher identity requires (human actions)

- A **Grafana Cloud account** (or at minimum a grafana.com account) to submit the
  plugin and hold the Access Policy Token used for signing.
- Agreement on the **org slug** the `id` field's prefix should use (this plugin
  guesses `intersystems`; InterSystems' developer relations/marketing should confirm
  this matches how InterSystems is represented elsewhere in Grafana's ecosystem, if
  at all yet).
- An **approved logo** (`info.logos.small`/`large`) — this plugin currently ships a
  generic scaffold placeholder icon, not InterSystems branding, and that must not go
  out under the InterSystems name without going through whatever brand-asset
  approval InterSystems requires.
- A decision on **Community vs. Commercial** positioning, which affects whether this
  is purely a community contribution or tied to an official InterSystems support
  commitment — that decision shapes what Grafana will grant on review, and is a
  business call, not an engineering one.
- Real **screenshots** and ideally a short demo video, captured against an actual
  running Grafana + IRIS pair — impossible to produce in this environment (no Docker
  daemon, no running IRIS; see STATUS.md).
- A decision on where this plugin's canonical repository lives long-term (see the
  placement caveat in `../README.md`) — the Grafana submission form wants a stable
  public GitHub URL, and `iris-ai-examples` is not intended to be that home.

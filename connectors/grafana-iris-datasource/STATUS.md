# STATUS

Read this before trusting anything else in this directory. Per the environment's
hard limits (`../README.md`): no running IRIS instance, no Docker daemon, no
third-party accounts or submissions were used to produce any claim below.

## VERIFIED

Every claim here is backed by a command actually run in this session; outputs below
are real, not reconstructed.

**Go backend builds clean, vets clean, and every test passes:**

```
$ go build ./...
PASS (exit 0)

$ go vet ./...
PASS (exit 0)

$ gofmt -l .
(no output — everything is gofmt-formatted)

$ go test ./... -cover
ok  .../pkg/plugin         (cached)  coverage: 89.5% of statements
ok  .../pkg/plugin/client  (cached)  coverage: 78.4% of statements
```

26 individual `--- PASS` assertions across two packages, `go version go1.24.7
linux/amd64`. (`go test ./...` also incidentally compiles a vendored Go file that
ships inside an npm dependency at `node_modules/flatted/golang/pkg/flatted` — Go's
`./...` pattern does not skip `node_modules`. It reports `coverage: 0.0%` because it
has no tests, and is not part of this plugin; harmless, but noted here in case a
future run of `go test ./...` looks odd.)

**What those Go tests actually exercise**, since "tests pass" is meaningless without
saying what they're testing:

- `pkg/plugin/client/rest_client_test.go` — a real `net/http/httptest.Server`
  standing in for IRIS, exercising: successful SQL query parsing, IRIS-reported SQL
  errors, HTTP 401/403 auth failures, an empty result set, `Ping` (health check),
  scraping `/api/monitor/metrics`, and — the one most worth calling out —
  `TestRESTClient_Query_PreservesColumnOrder`, which pins down that column order in
  the returned frame follows the original SQL SELECT list order rather than
  whatever order Go's JSON decoder or map iteration would otherwise produce (Go's
  `encoding/json` always alphabetizes map keys on marshal, which would have
  silently reordered columns without the raw-byte token-walking in
  `firstRowKeyOrder`).
- `pkg/plugin/client/metrics_parser_test.go` — the hand-written OpenMetrics/
  Prometheus text parser: labeled and bare metric lines, comma-inside-quoted-label
  values, and that malformed lines are skipped rather than failing the whole scrape.
- `pkg/plugin/models_test.go` — config parsing and defaults, and a regression test
  (`TestLoadPluginSettings_NeverReadsPasswordFromPlainJSONData`) that the password is
  never read from `jsonData`, only from `DecryptedSecureJSONData["password"]`.
- `pkg/plugin/frame_test.go` — SQL-result-to-`data.Frame` type inference (bool,
  numeric, timestamp-string, and mixed-type-falls-back-to-string columns; an
  all-NULL row doesn't break typing), and the SAM-metrics wide-table frame shape.
- `pkg/plugin/datasource_test.go` — `QueryData` dispatch for both query types plus
  an unknown query type, `CheckHealth` success/failure, and a hand-written fake
  `client.IRISClient` (there is no real IRIS to talk to, so this fake is what every
  datasource-layer test actually runs against).

**Go cross-compilation for three targets, run in this session:**

```
$ GOOS=linux   GOARCH=amd64  go build -o dist/gpx_iris_datasource_linux_amd64   .
linux_amd64 OK
$ GOOS=darwin  GOARCH=arm64  go build -o dist/gpx_iris_datasource_darwin_arm64  .
darwin_arm64 OK
$ GOOS=windows GOARCH=amd64  go build -o dist/gpx_iris_datasource_windows_amd64.exe .
windows_amd64 OK
```

(Binaries were deleted after verification — they're large, regenerable, and not
meant to be committed; see `.gitignore`. Re-run the three commands above to
reproduce.)

**Frontend typechecks, builds, and its own tests pass:**

```
$ npm install
added 1199 packages, and audited 1200 packages in 2m
(8 vulnerabilities: 3 moderate, 5 high — all in devDependencies pulled in by the
 @grafana/create-plugin-scaffolded webpack/eslint toolchain, not in this plugin's
 own code or its two runtime dependencies; not triaged further in this session)

$ npm run typecheck   # tsc --noEmit
(no output — clean)

$ npm run build       # webpack -c ./.config/webpack/webpack.config.ts --env production
webpack 5.111.0 compiled successfully in ~200ms
assets: module.js, module.js.map, plugin.json, README.md, CHANGELOG.md, LICENSE,
        img/logo.svg

$ npx jest --passWithNoTests
Test Suites: 2 passed, 2 total
Tests:       7 passed, 7 total
```

The 7 frontend tests (`src/components/ConfigEditor.test.tsx`,
`src/components/QueryEditor.test.tsx`, React Testing Library) check: the SQL text
area only shows for `queryType: 'sql'`, changing it calls `onChange` with the new
`queryText`, switching to `sam_metrics` calls `onRunQuery`, and — the security-
relevant one — that editing the host field never touches `secureJsonData` and
editing the password field never touches plain `jsonData`.

**Node/Go/npm versions used:** `go1.24.7 linux/amd64`, `node v22.22.2`, `npm 10.9.7`.

**Module pinning:** `grafana-plugin-sdk-go` is pinned to v0.280.0 (not `@latest`,
which is v0.296.4) specifically because v0.296.4 requires Go ≥1.26.5 and this
environment has Go 1.24.7 available; v0.280.0 requires Go ≥1.24.6, which matches
without a toolchain re-download.

**`caretdev/grafana-intersystems-datasource` was read via read-only GET only** — its
README/repo structure were fetched for the comparison in README.md's Attribution
section; no code from it was copied into this plugin.

## UNVERIFIED

- **Nothing here was run against a real IRIS instance.** The REST/SQL request and
  response shapes in `pkg/plugin/client/rest_client.go` — the exact JSON body of
  `POST /api/atelier/v1/{namespace}/action/query`, and that `result.content` really
  is "array of row-objects keyed by column name" rather than some other shape — are
  based on InterSystems community-forum posts and search-result summaries (cited in
  README.md), not on a fetch of `docs.intersystems.com` (blocked by the environment's
  egress proxy) or on an actual IRIS response. If the real shape differs even
  slightly (e.g. numbers coming back as JSON strings instead of numbers, or an error
  shape other than `status.errors`), `Query()` will misbehave in ways the offline
  tests cannot catch, because the tests' fake server was written to match the same
  assumption. Same caveat for `/api/monitor/metrics` being plain OpenMetrics/
  Prometheus text with no auth quirks beyond HTTP Basic.
- **The plugin has never been loaded into a real Grafana.** `datasource.Manage`,
  the gRPC handshake, and the frontend's `DataSourcePlugin` registration all come
  from grafana-plugin-sdk-go and `@grafana/data` and compile/typecheck cleanly, but
  "compiles" is not "Grafana successfully loads and runs it." No screenshot of the
  config editor, query editor, or a working panel exists.
- **The three cross-compiled binaries were built and deleted; none was executed.**
  `go build` succeeding for `windows_amd64`/`darwin_arm64` from a `linux_amd64` host
  only proves it compiles for that target, not that it runs there.
- **`docker-compose.yaml` and `provisioning/datasources/datasources.yml`** (copied
  from the `@grafana/create-plugin` scaffold and adapted with IRIS-shaped
  `jsonData`/`secureJsonData`) were never run — there is no Docker daemon in this
  environment.
- **`npm audit`'s 8 reported vulnerabilities** were not individually triaged; they
  are scoped to `devDependencies` in the scaffolded build toolchain (webpack/eslint
  plugin chain), not to this plugin's two runtime dependencies (`react`,
  `react-dom`) or its own code, but that is an inference from where they were
  installed from, not a line-by-line audit.
- **eslint/prettier were never run** on this code (only `tsc --noEmit`, `jest`, and
  `webpack --env production`, all of which passed). Style issues are possible.
- **The `%VERSION%`/`%TODAY%` placeholders** in `src/plugin.json` are filled in by
  the webpack build (confirmed: the built `dist/plugin.json` had real values after
  `npm run build`), but the actual version string it produced was never inspected
  against what Grafana's catalog would expect for a first submission (typically
  `0.1.0`-style semver matching `package.json`, which this does — just not
  independently double-checked field-by-field against a real catalog submission).
- **Everything in PUBLISHING.md** is desk research assembled from search-engine
  snippets of Grafana's own `plugin-tools`/`grafana-plugin-repository` GitHub repos,
  the `@grafana/sign-plugin` npm page, and Grafana Labs community-forum threads —
  `grafana.com` itself was blocked by this environment's egress proxy for direct
  fetches. Re-verify against the live docs before submitting for real.

## HUMAN ACTIONS REQUIRED

- **Stand up a real IRIS instance and a real Grafana instance** and point this
  plugin at it (via `docker-compose.yaml` + `provisioning/datasources/` as a
  starting point, or manually) to actually validate the REST/SQL response-shape
  assumptions in the UNVERIFIED section above. This is the single highest-value
  next step — if the Atelier API response shape is wrong, it's a small, localized
  fix in `rest_client.go`, but it needs a real IRIS to find.
- **Decide the plugin's long-term home.** Per `../README.md`'s placement caveat,
  `iris-ai-examples` is demo-example staging, not where a production Grafana plugin
  should live long-term. Someone needs to pick (or create) its real repository
  before it can be submitted to the Grafana catalog, which wants a stable public
  GitHub URL.
- **Create/identify the Grafana Cloud (or grafana.com) account** that will hold the
  Access Policy Token used to sign the plugin and that will submit it for catalog
  review — this task's hard rules explicitly forbid creating any such account or
  submitting anything in this session.
- **Supply an approved InterSystems/IRIS logo.** `src/img/logo.svg` is currently a
  generic `@grafana/create-plugin`-scaffolded placeholder icon (a stylized grid
  motif, not InterSystems branding) and must not ship to the public catalog as-is.
- **Resolve the relationship with `caretdev/grafana-intersystems-datasource`**
  before submitting — see PUBLISHING.md §5. An unpublished, near-duplicate plugin by
  another author already existing is a predictable rejection risk during Grafana's
  manual review unless it's addressed head-on in the submission (coordination,
  supersession, or a clear differentiation).
- **Capture real screenshots/a demo video** of the config editor, query editor, and
  a working dashboard panel against live IRIS + Grafana, for the README and the
  catalog's `info.screenshots`. Impossible to produce here — no running Grafana UI
  existed in this session, only unit and build-level verification.
- **Decide Community vs. Commercial signature-level positioning** (PUBLISHING.md
  §4/§6) — a business decision about InterSystems' relationship to Grafana, not an
  engineering one, and it affects what the plugin can be submitted as.
- **Triage the 8 `npm audit` findings** in the frontend devDependency tree before
  treating the build pipeline as production-ready CI, even though none are in this
  plugin's own runtime dependencies.
- **Run `eslint`/`prettier`** (configs are in place at `.config/eslint.config.mjs`
  and `.prettierrc.js`, wired into `package.json`'s `lint`/`lint:fix` scripts) —
  not run in this session.

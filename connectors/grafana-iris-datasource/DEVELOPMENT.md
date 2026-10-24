# Development guide

For people changing the plugin. Users should read README.md.

## Layout

- `src/` is the browser half (TypeScript, React): the query editor, the settings page, and `datasource.ts`, which
  interpolates dashboard variables.
- `pkg/` is the server half (Go): `pkg/plugin` turns queries into IRIS calls and results into Grafana data frames,
  `pkg/plugin/client` talks to IRIS over its REST API. `pkg/main.go` is the entry point the build expects.
- `docs/SPEC.md` and `docs/TASKS.md` say what the plugin must do and what is left. `docs/VERIFICATION.md` records
  what was measured against a real IRIS and Grafana. `docs/research/` holds the catalog requirements.

## Build and test

You need Node 22 or later and the Go version in `go.mod`.

```bash
npm ci && npm run typecheck && npm run lint && npm run test:ci   # browser half
go vet ./... && go test ./...                                    # server half, with fakes
npm run build && go run github.com/magefile/mage buildAll        # fills dist/
```

## Tests against a real IRIS and a real Grafana

The fakes in the unit tests were written from the same assumptions as the code, so they cannot disagree with it.
The suites below can, and found the plugin's most serious bugs.

```bash
docker compose -f docker-compose.e2e.yaml up -d --wait          # a disposable IRIS on :33273
IRIS_URL=http://localhost:33273 IRIS_USER=_SYSTEM IRIS_PASSWORD=SYS \
  go test -tags e2e -count=1 ./pkg/...                          # fails, not skips, without the variables

./e2e/seed.sh                                                    # demo data for the dashboard
./e2e/seed-showcase.sh                                           # synthetic Tenant events for /d/iris-showcase
GRAFANA_VERSION=11.1.0 docker compose -f docker-compose.grafana.yaml up -d --wait   # Grafana on :33000
GRAFANA_VERSION=13.2.3 GRAFANA_E2E_PORT=33001 \
  docker compose -p grafana-iris-ds-13 -f docker-compose.grafana.yaml up -d --wait  # a second one on :33001
```

Open `http://localhost:33000/d/iris-demo` and `/d/iris-showcase`. Grafana is anonymous Admin in this stack: it is
for local testing only. The e2e suite runs every query in the showcase dashboard, so seed it before the suite.

```bash
./e2e/tenant-isolation.sh                                        # Tenant isolation through Grafana on :33000
GRAFANA_URL=http://localhost:33001 ./e2e/tenant-isolation.sh     # and on :33001
TENANT_TRANSPORT=rest ./e2e/tenant-isolation.sh                  # the control: must exit 1
```

The terminal transport (`pkg/plugin/client/terminal_*.go`) rests on three things measured against IRIS 2026.1, each
pinned by a test. A terminal line of 427 characters or more is dropped with no output, so everything goes over in
short base64 chunks. A WebSocket without the CSP session cookie holds a licence slot until its session times out,
so one cookie is seeded with `GET /api/atelier/` and shared. And the terminal discards input that arrives while it
is busy, so each line waits for its prompt.

### The browser cache trap

Grafana serves a plugin's `module.js` with a cache key made from the plugin **version**. After you rebuild the
frontend, your browser keeps running the old file until the version changes. Reload with the cache disabled, or
open the page in a fresh browser profile. A rebuilt backend binary needs `docker restart` of the Grafana container.

## Packaging and the validator

```bash
scripts/package.sh        # builds everything and writes dist-zip/intersystems-iris-datasource-<version>.zip
npx -y @grafana/plugin-validator@latest -sourceCodeUri file://. dist-zip/*.zip
```

Run `package.sh` last: it regenerates the source manifest the validator checks, so editing a Go file afterwards
fails the `go-manifest` check.

## Things that are not obvious

- **Timestamps.** A `TIMESTAMP` column created with SQL DDL is a PosixTime. REST returns its internal value
  (unix microseconds plus 2^60) and compares it correctly only against `CAST('...' AS TIMESTAMP)`.
- **NULL.** REST sends `""` for a NULL string or time and `0` for a NULL number.
- **Permissions.** `/api/atelier` needs `%Development` and then ignores table privileges, which is why the plugin
  refuses non-SELECT statements itself (`pkg/plugin/readonly.go`).
- **Go SDK age.** The validator makes an SDK older than five months an Error; update it before each release.
- **Validator and npm advisories.** The validator fails on any high-severity advisory in the lockfile. `braces`
  has one with no patched version at the time of writing, which cannot be fixed from here.

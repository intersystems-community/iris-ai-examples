# integration_tests/

These files follow Airbyte's standard connector directory convention (a `secrets/`
directory holding real, gitignored credentials as `config.json`, plus non-secret
fixtures here), but **none of them have been run against a live IRIS instance or
through Docker-based Connector Acceptance Tests** — there is no running IRIS and no
Docker daemon in this environment. See `../STATUS.md`.

- `sample_config.json` — a non-secret template showing the config shape; copy it to
  `secrets/config.json` and fill in real credentials to actually run CAT or manual
  `check`/`discover`/`read` against a live IRIS instance.
- `invalid_config.json` — deliberately missing the required `password` field, used by
  `acceptance-test-config.yml`'s `connection` test to assert `check` reports `FAILED`.
- `configured_catalog.json` — illustrative `ConfiguredAirbyteCatalog` matching the demo
  tables used throughout `../unit_tests/` (`SQLUser.Patient` incremental on `ID`,
  `SQLUser.Note` full-refresh-only). Whoever runs this against a real IRIS instance
  will need to first create these tables (or edit this file to match real tables) —
  it is not a fixture that provisions its own data.

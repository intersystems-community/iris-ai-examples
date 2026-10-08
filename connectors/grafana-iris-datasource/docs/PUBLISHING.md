# Publishing to the Grafana catalog (Phase B)

Source of truth for the rules: `docs/research/grafana-catalog-requirements.md`. This is the order of work.

## Blocked on a decision

1. **Publisher identity.** The plugin id must start with the slug of a Grafana Cloud organisation you administer.
   `intersystems` looked unclaimed on 2026-10-08. Sign up (a forever-free account is enough to begin), read the
   slug off the new organisation's page, and change the id if it differs: `src/plugin.json`, `package.json`,
   `pkg/main.go` constants and the provisioning files.
2. **Signature class.** Grafana's policy reads as if a for-profit vendor gets a Commercial signature (a paid
   subscription) rather than Community. Ask `integrations@grafana.com` before relying on either.
3. **Ownership line.** `LICENSE` now says "Copyright 2026 InterSystems Corporation". Confirm that is right.

## Then

4. Extract the plugin to its own repository with history (`git subtree split`). The workflow in `.github/workflows`
   only runs from a repository root.
5. Keep the Go SDK within two months of the latest release when you submit.
6. Create an access policy with scope `plugins:write` for the organisation and store it as a CI secret.
7. Tag a release; CI runs `scripts/package.sh`, the validator, and the Grafana matrix; sign with
   `npx @grafana/sign-plugin@latest --rootUrls ...` for a private build.
8. Submit under Org Settings, My Plugins, Submit New Plugin: zip URL, source tag, SHA-1, and testing guidance
   (the compose files in this directory start an IRIS and a seeded dashboard).
9. Answer reviewer questions; expect them to test against their own IRIS.

## Things to raise with Grafana

- The `braces` advisory above blocks the validator's `osv-scanner` for every plugin that uses jest or eslint.
- Whether a data source whose backend reaches a database over the database's own REST API, with a read-only guard
  in the plugin rather than in the database, is acceptable.

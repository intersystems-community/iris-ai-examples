# Keycloak fixture for the OAuth2 RBAC example

The IdP half of [`Sample.AI.OAuth`](../../objectscript/cls/Sample/AI/OAuth/README.md).
Three client-credentials clients, one per role tier, in a realm you can throw away.

The measured results in that README came from this configuration. It is here so the
matrix can be re-run rather than taken on trust.

## Start it

```bash
docker compose up -d --wait
./get-token.sh read
```

The realm imports on first start. `docker compose down -v` and up again resets it,
because `start-dev` keeps its H2 database inside the container.

| Setting            | Default                                     |
| ------------------ | ------------------------------------------- |
| `KEYCLOAK_PORT`    | `55880` (host)                              |
| `KEYCLOAK_NETWORK` | `aihub-oauth-demo`                          |
| Admin console      | <http://localhost:55880/> — `admin`/`admin` |
| Realm              | `aihub`                                     |

## What the realm contains

| Client      | Secret         | Default scopes              | Maps to IRIS role |
| ----------- | -------------- | --------------------------- | ----------------- |
| `mcp-read`  | `read-secret`  | `mcp.audience`, `mcp.read`  | `SampleReader`    |
| `mcp-write` | `write-secret` | `mcp.audience`, `mcp.write` | `SampleWriter`    |
| `mcp-admin` | `admin-secret` | `mcp.audience`, `mcp.admin` | `SampleAdmin`     |

All three are confidential, service-accounts-only: no browser flow, no direct grant,
no user. The secrets are in this file on purpose — it is a fixture, and nothing it
guards exists outside a demo container.

`mcp.read` / `mcp.write` / `mcp.admin` carry no mappers. Their whole job is
`include.in.token.scope: true`, which is what puts the string in the token's `scope`
claim for `ScopeAuthenticator` to read.

`mcp.audience` is the opposite: `include.in.token.scope: false`, one
`oidc-audience-mapper` putting `mcp-api` in `aud`. Keycloak does not add an audience
for a client-credentials token on its own, and IRIS rejects a token whose `aud` is not
in `OAuth2.ResourceServer.Audiences` — with an error that does not say "audience". If
you rename the audience here, rename it there too.

## Wiring IRIS to it

Put your IRIS container on the same network (`aihub-oauth-demo`), then fill in the
records `Sample.AI.OAuth.Setup.CreateSkeleton()` scaffolds:

| Record                                | Field            | Value                                                  |
| ------------------------------------- | ---------------- | ------------------------------------------------------ |
| `OAuth2.ServerDefinition`             | `IssuerEndpoint` | `http://aihub-oauth-keycloak:8080/realms/aihub`        |
| `OAuth2.ServerDefinition`             | `PublicJWKS`     | the JSON from `<issuer>/protocol/openid-connect/certs` |
| `OAuth2.ResourceServer`               | `Audiences`      | `mcp-api`                                              |
| `OAuth2.ResourceServer.Authenticator` | `Implementation` | `Sample.AI.OAuth.ScopeAuthenticator`                   |

The container name, not `localhost`, in both the issuer and the JWKS URL. `iss` is
compared as a string, and a token minted for one hostname fails against a definition
stored under another — the most common first failure with this example.

Fetch the JWKS with the port published on the host, and it will still be the right
key material for the container-name issuer:

```bash
curl -s http://localhost:55880/realms/aihub/protocol/openid-connect/certs
```

## Reproducing the README's matrix

```bash
# from ai-hub/
pytest tests/integration/test_oauth_live_idp.py -v
```

That suite skips unless both this IdP and an MCP endpoint answer. See its module
docstring for the two environment variables it needs.

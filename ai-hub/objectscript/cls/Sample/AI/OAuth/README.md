# OAuth2 RBAC Example — Sample.AI.OAuth

Role-based access control on an IRIS MCP server, driven by an OAuth2 bearer token from an
external IdP. The token's scopes decide which IRIS roles the caller gets, and those roles
decide which tools the caller can see and run. No manual JWT parsing — IRIS's own
`OAuth2.ResourceServer` validates the token.

Tools are gated at two levels:

- **Catalog filtering**: `tools/list` returns only the tools the caller's roles permit.
- **Execution enforcement**: `tools/call` is denied when the caller lacks the required
  role, even for a hand-built request.

Measured end to end on IRISHealth 2026.3.0AI build 139U (arm64) against Keycloak 26 — see
[What was measured](#what-was-measured).

## Prerequisites

- IRIS 2026.3+ with the `%AI` MCP classes.
- `iris-mcp-server` (the MCP sidecar) pointed at the endpoint, with **no** endpoint-level
  credentials configured — the client's own `Authorization: Bearer` header is what this
  example reads.
- An external IdP with a JWKS endpoint. Verified against Keycloak 26; Cognito, Auth0 and
  Entra expose the same claims.
- Catalog filtering needs the 2-argument `%CanList`, which 139 has. See
  [Build version notes](#build-version-notes).

## Quick Start

### Step 1: Scaffold OAuth2 records

From an IRIS terminal in your working namespace:

```objectscript
Do ##class(Sample.AI.OAuth.Setup).CreateSkeleton()
```

This creates placeholder `OAuth2.ServerDefinition` and `OAuth2.ResourceServer` records and
prints the fields you must fill in.

### Step 2: Fill in IdP values

Edit the records created in step 1:

1. Set `OAuth2.ServerDefinition.IssuerEndpoint` to your IdP's issuer URL. It must match
   the token's `iss` claim exactly, hostname included.
2. Set `OAuth2.ServerDefinition.PublicJWKS` to the JSON from your IdP's
   `/.well-known/jwks.json` endpoint.
3. Set `OAuth2.ResourceServer.Audiences` to the audience your IdP puts in the token's
   `aud` claim.
4. Set `OAuth2.ResourceServer.Authenticator.Implementation` to
   `Sample.AI.OAuth.ScopeAuthenticator`, or your own — see
   [Authenticator pattern](#authenticator-pattern).

### Step 3: Register roles, the web application and the mapping

```objectscript
Do ##class(Sample.AI.OAuth.OAuthMCPService).SetupService()
```

One call does all of it: creates the three tier roles, creates the validator role the auth
hook needs ([why](#the-validator-role)), registers the web application at `Type = 19`, and
wires the `OAuth2.ResourceServer.Mapping`. Idempotent.

The path comes from the `ServicePath` parameter, not from an argument. Three things are
keyed on that string — the web application name, the Mapping key, and the `info` argument
to `ValidateConnection` — so override the parameter in a subclass rather than passing a
different path.

### Step 4: Verify

```objectscript
Do ##class(Sample.AI.OAuth.OAuthMCPService).VerifyPrerequisites()
```

Seven checks, each printing `OK:` or `FAIL:` with what to run to repair it.

### Step 5: Drive it with a real token

Get a token from your IdP, then run the MCP handshake against the sidecar. `initialize`
first — the `mcp-session-id` it returns is required on every later request.

If you brought up [`fixtures/keycloak`](../../../../../fixtures/keycloak/README.md),
`./get-token.sh read` is the first line. Otherwise:

```bash
TOKEN=$(curl -s -X POST http://localhost:55880/realms/aihub/protocol/openid-connect/token \
  -d grant_type=client_credentials -d client_id=mcp-read -d client_secret=... \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

H=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
   -H "Authorization: Bearer $TOKEN")

SID=$(curl -s -D - -o /dev/null "${H[@]}" -X POST http://localhost:8888/mcp/sampleoauth \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  | grep -i '^mcp-session-id:' | tr -d '\r' | awk '{print $2}')

H+=(-H "Mcp-Session-Id: $SID")
curl -s "${H[@]}" -X POST http://localhost:8888/mcp/sampleoauth \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
curl -s "${H[@]}" -X POST http://localhost:8888/mcp/sampleoauth \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Replies arrive as SSE (`data: {…}`) rather than a plain JSON body.

## Role / Tool Mapping

Measured, not intended — this is what the three tiers actually returned from `tools/list`:

| Token scope   | IRIS roles after the hook | Tools in `tools/list`            |
| ------------- | ------------------------- | -------------------------------- |
| `mcp.read`    | `%DB_USER,SampleReader`   | `GetStatus`                      |
| `mcp.write`   | `%DB_USER,SampleWriter`   | `WriteNote`                      |
| `mcp.admin`   | `%DB_USER,SampleAdmin`    | `AdminReset`                     |
| invalid token | — (connection refused)    | _(endpoint contributes nothing)_ |
| no token      | — (sidecar returns 401)   | _(no MCP session at all)_        |

Roles are not hierarchical here. Grant multiple scopes to expose multiple tiers.

A caller whose token validates but carries no mapped scope is **refused**, not given an
empty catalog. An empty tool list is indistinguishable from a broken endpoint, so it is a
bad way to say "denied".

## How It Works

```text
Client sends: Authorization: Bearer <JWT>
                    │
                    ▼
        iris-mcp-server (sidecar), no endpoint credentials
        passes the header through; connects over the superserver
                    │
                    ▼
        Web application /mcp/sampleoauth, Type = 19
        MatchRoles grants SampleOAuthValidator
                    │
                    ▼
        %AI.MCP.Service.OnAuthenticate(authType, auth)   ← the gate
                    │
                    ▼
        OAuth2.ResourceServer.ValidateConnection(...)     ← called from %SYS
        validates signature, issuer, audience
                    │
                    ▼
        ScopeAuthenticator.DetermineRoles(claims)
        maps "mcp.read" → "SampleReader", returns it in properties("Roles")
                    │
                    ▼
        Set $Roles = "%DB_USER,SampleReader"              ← replaces, not adds
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
 RoleDiscovery  RBACPolicy  OTelAuditPolicy
 %Resolve()     %CanExecute()  %LogExecution()
 (tools/list)   (tools/call)   (every call)
```

`AutheEnabled` is not on that path. See [Build version notes](#build-version-notes).

The policy classes (`RBACPolicy`, `RoleDiscovery`) only read `$Roles`. They know nothing
about your IdP, the JWT, or the authenticator class.

`DemoToolSet` also attaches `Sample.AI.Policies.OTelAuditPolicy`, so every `tools/call`
emits a `gen_ai.tool_call` span. Two things about that span, measured on the MCP path:
the framework passes `duration = 0` and the literal call id `"call_id"`, so it is a point
in time and correlates nothing. Both carry real values when the same policy runs behind
`%AI.Agent`.

## Authenticator Pattern

The authenticator turns validated claims into IRIS role names. Three things about this
hook are easy to get wrong:

1. It **must** extend `%OAuth2.ResourceServer.Authenticator` or a subclass.
   `OAuth2.ResourceServer.AuthenticatorSet` constructs it with
   `$classmethod(Implementation, "%New", val)` and then calls `Serialize()` on it, so a
   plain `%RegisteredObject` fails at `%Save()` time with `<ILLEGAL VALUE>` — not at
   compile time, and with no error that names the superclass.
2. Roles are returned **through the properties array**, not by mutating the session.
   Calling `%SYS.Session.AddRoles()` from here does not do what the name suggests.
3. Most of the work is already shipped. `%OAuth2.ResourceServer.SimpleAuthenticator`
   reads the username from `UserClaim` and splits `RoleClaim` on spaces. If your IdP
   already emits IRIS role names, configure that class and write no ObjectScript at all.

`Sample.AI.OAuth.ScopeAuthenticator` exists for the common case where it does not — where
the scope strings (`mcp.read`) and the role names (`SampleReader`) are different
vocabularies:

```objectscript
Class My.OAuth.Authenticator Extends %OAuth2.ResourceServer.SimpleAuthenticator
{

Parameter SCOPEMAP As STRING = "mcp.read=SampleReader,mcp.write=SampleWriter";

/// Signature is inherited untyped — do not add a type to claims.
Method DetermineRoles(claims) As %String
{
    // ... map claims.%Get("scope") to a comma-separated role list
    Return tRoles
}

}
```

Wire it into the Resource Server:

```objectscript
New $Namespace
Set $Namespace = "%SYS"
Set tRS = ##class(OAuth2.ResourceServer).%OpenId("SampleOAuth")
Set tAuth = {"Implementation":"Sample.AI.OAuth.ScopeAuthenticator",
             "Namespace":"USER","UserClaim":"sub","RoleClaim":"scope"}
Set tRS.Authenticator = tAuth
Do tRS.%Save()
```

## The Validator Role

This is the uncomfortable part of the example, so it is written down rather than buried.

`OnAuthenticate` runs before the caller has any identity — `$Username` is `UnknownUser`.
The privilege to validate a token therefore has to come from the web application's
`MatchRoles`. `SetupService` creates `SampleOAuthValidator` with the measured minimum,
found by bisecting resource by resource on build 139U:

| Resource                 | Without it                                                            |
| ------------------------ | --------------------------------------------------------------------- |
| `%DB_IRISSYS:R`          | `ValidateConnection` raises `<PROTECT>` on `/usr/irissys/mgr/`        |
| `%DB_IRISSYS:RW`         | `Set $Roles` raises `<PROTECT>`, even to _drop_ a role                |
| `%Admin_Secure:U`        | `ValidateConnection` returns `#822: Access Denied`, naming nothing    |
| `%Admin_OAuth2_Client:U` | `ValidateConnection` raises `<INVALID OREF>` in `ValidateAccessToken` |

A resource server needing the OAuth2 **client** resource is not obvious from the name.
Nothing narrower worked: `%Manager` works and `%Developer` does not; `%DB_IRISSYS:RW` plus
`%Admin_Secure` but no OAuth2 resource fails, and with an OAuth2 resource but no
`%Admin_Secure` fails.

Write access to the security database is real privilege. Read this as "the MCP endpoint is
trusted code", not as least privilege. Two consequences worth stating:

- The hook **replaces** `$Roles` rather than adding to it, so the validator privilege does
  not survive into tool execution. Adding would also disable the catalog filter, because
  `RoleDiscovery` short-circuits on `%All`.
- Because the application grants privilege before any token is checked, a hook that
  returned `$$$OK` on a validation failure would be a genuine hole. It returns an error
  status, and the connection is refused.

## What Was Measured

Driven against Keycloak 26 on IRISHealth 2026.3.0AI build 139U (arm64), through
`iris-mcp-server`, with client-credentials tokens.

Keycloak side: realm `aihub`; three clients `mcp-read` / `mcp-write` / `mcp-admin`, each
with service accounts enabled and a default scope of `mcp.read` / `mcp.write` /
`mcp.admin`; an `oidc-audience-mapper` putting the resource server's audience in `aud`.
`KC_HOSTNAME` is pinned so the `iss` claim matches what IRIS has stored — a mismatch there
is the most common first failure. That configuration is checked in at
[`fixtures/keycloak`](../../../../../fixtures/keycloak/README.md), and
`tests/integration/test_oauth_live_idp.py` re-runs the matrix below against it — 15 tests,
host-side, no `irispython`, skipped unless both the IdP and the endpoint answer.

Results:

- One tool per tier from `tools/list`, for all three tiers.
- `properties("Username")` is the service account's `sub`.
- A garbage bearer token is refused: the endpoint contributes no tools.
- No `Authorization` header at all never reaches IRIS — the sidecar answers 401.
- `tools/call` of the tier's own tool succeeds and returns the stub string.

**Catalog filtering held per client session.** Four client connections in a row with
different tiers, against one running sidecar, each got exactly its own tool — no restart
between them. The sidecar logs a fresh `Discovered 1 tool(s) from /mcp/sampleoauth` per
client connection, so the catalog is built with that client's token. An earlier note here
said filtering was advisory because `iris-mcp-server` kept one shared registry per
endpoint; that was measured on a different build and does not reproduce on this one. If you
depend on the per-session behaviour, verify it on your own sidecar version.

**One catalog covers the whole sidecar.** `tools/list` returns this endpoint's tools
alongside every other configured endpoint's, plus the sidecar's own `iris_status`. So
"the read tier sees one tool" is a claim about the `mcp_sampleoauth_` prefix, not about
the length of the list. A test that counts the whole catalog measures how many endpoints
are configured.

**Swapping the token mid-session empties the endpoint.** Send a different bearer token on
a live session and this endpoint contributes nothing — including when the new token is a
fresh token for the same tier, and including when it is a higher tier. It fails closed
rather than escalating, and it recovers: send the original token again and the tool is
back. This matters for clients that refresh tokens on a timer rather than per connection,
because the refresh does not re-authorize the session, it silently empties it.

**`tools/call` of an unlisted tool is refused by the sidecar first.** A read-tier client
calling `AdminReset` gets `Service unavailable: no registered service found` — the tool is
not in that session's registry, so `RBACPolicy.%CanExecute` is never reached. Execution
enforcement is defence in depth behind the catalog, not the first line of it. The unit
tests cover its deny path directly.

## Build Version Notes

Measured on 2026.3.0AI build 139U (arm64) by reading `%Dictionary.CompiledMethod`:

| Feature                               | Hook the build actually ships                                                                                 |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| The auth gate                         | `%AI.MCP.Service.OnAuthenticate(authType, auth)` — a **ClassMethod**                                          |
| Execution enforcement (`%CanExecute`) | `%AI.Policy.Authorization.%CanExecute(tool, call, metadata)` — present                                        |
| Catalog filtering (`%CanList`)        | `%AI.Policy.Authorization.%CanList(tool, metadata)` — present, 2-arg                                          |
| Catalog rewrite                       | `%AI.Policy.Discovery.%Resolve(catalog As %DynamicArray)` — present                                           |
| Token validation                      | `OAuth2.ResourceServer.ValidateConnection(service, info, token, &props)` returns **`%Status`**, not a boolean |

An earlier version of this README said catalog filtering needed build 148+. Not true of 139. If you are on an older build, check the signature yourself rather than trusting a
floor number — one query against `%Dictionary.CompiledMethod` settles it.

Three sharp edges on this build, all measured:

- **`AutheEnabled` does not gate the MCP path, in either direction.** At `67108864`
  (AutheOAuth2 alone) every request is refused with `Unauthorized: Authentication
required`, valid token or not. At `67108928` (AutheOAuth2 + Unauthenticated) every
  request is admitted with no token check at all. `SetupService` therefore registers the
  application with `AutheEnabled = 96` and does the checking in `OnAuthenticate`.
- **`Type = 19` is load-bearing** (MCP 16 + CSP 2 + 1). At `Type = 18` the application's
  `MatchRoles` never reaches the MCP session, so the hook has no privilege and nothing
  logs a reason. There is no `Roles` property on `Security.Applications` here;
  application roles are expressed as `MatchRoles = ":role1:role2"`.
- **`OAuth2.ResourceServer` is not mapped outside `%SYS`.** Calling it from the
  application namespace raises `<CLASS DOES NOT EXIST>`. `New $Namespace` fixes that, but
  it unwinds at _method_ exit, not at `Try` exit — so the `%SYS` call belongs in its own
  method or an error handler runs in `%SYS` and dies on the first thing it touches.

`%SYS.OAuth2.Validation.ValidateJWT` is not the API for this. It wants an `OAuth2.Client`
config and returns `#5809: Object to Load not found, class 'OAuth2.Client'`.

## Classes in This Package

| Class                                | Purpose                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| `Sample.AI.OAuth.OAuthMCPService`    | MCP service — `OnAuthenticate` gate, roles, web app and RS mapping            |
| `Sample.AI.OAuth.ScopeAuthenticator` | Maps OAuth2 scopes to IRIS role names                                         |
| `Sample.AI.OAuth.RoleDiscovery`      | Discovery policy — filters the `tools/list` catalog by `$Roles`               |
| `Sample.AI.OAuth.RBACPolicy`         | Authorization policy — gates `%CanList` and `%CanExecute` by `$Roles`         |
| `Sample.AI.OAuth.DemoToolSet`        | Demo ToolSet — 3 stub tools at Reader / Writer / Admin tiers                  |
| `Sample.AI.Policies.OTelAuditPolicy` | Audit policy — one `gen_ai.tool_call` span per call (lives in `AI/Policies/`) |
| `Sample.AI.OAuth.Setup`              | Setup utilities — `CreateSkeleton`, `PrintChecklist`                          |

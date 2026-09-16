# PUBLISHING.md

Concrete submission steps for each of the three directories the task named,
what an InterSystems-owned submission specifically needs that this session
could not provide, and — the actual decision this document exists to make —
**which server should be submitted.**

## The call: submit AI Hub's `iris-mcp-server`, not this reference implementation

**Recommendation: InterSystems should submit its own AI Hub `iris-mcp-server`
(shipping in IRIS 2026.x) to all three directories, not `mcp-iris` from this
repo.**

Reasoning:

1. **Directory-listing legitimacy needs an owner who can answer for the
   server in production.** The MCP registry's own namespace-authentication
   rule makes this literal: publishing under `io.github.intersystems-community/...`
   or a domain-based `com.intersystems/...` namespace requires proving
   control of that GitHub org or domain
   (`docs/reference/server-json/official-registry-requirements.md`,
   fetched from `raw.githubusercontent.com/modelcontextprotocol/registry`
   in this session). This repo (`iris-ai-examples`) is explicitly a
   **reference/demo repo** per its own `CLAUDE.md` and `AGENTS.md` — it is
   not the AI Hub product repo, and this session has no InterSystems
   organizational credentials to authenticate a real publish as
   InterSystems, nor should it.
2. **The Claude Connectors Directory (the claude.ai one, for remote
   servers) requires Streamable HTTP + OAuth 2.0 with a real user-consent
   flow**, per `claude.com/docs/connectors/building/submission` (confirmed
   via search snippets in this session; the docs domain itself returned
   `EGRESS_BLOCKED` when fetched directly — see `STATUS.md`). This
   reference server is **stdio-only by design**, matching the task's
   explicit instruction ("Python, using the official `mcp` SDK ..., stdio
   transport"). AI Hub's `iris-mcp-server`, being a real IRIS-hosted HTTP
   gateway (`/mcp/...` endpoints, per `AGENTS.md`'s existing
   `CareConnect.MCP.Service`/`KGTicketResolver.MCP.Service` pattern), is
   the one that can plausibly be stood up as a Streamable-HTTP,
   OAuth-fronted endpoint without a rewrite.
3. **ChatGPT's Apps SDK submission requires a public HTTPS `/mcp` endpoint
   with domain verification** (`developers.openai.com/apps-sdk/...`, same
   caveat on direct-fetch access). Same structural mismatch as above: a
   stdio server has no domain to verify.
4. **Community-maintainer risk is exactly what the task's own research
   document flags.** `research/ecosystem-connector-gaps.md` names
   `caretdev/mcp-server-iris` as one of several single-maintainer-risk
   packages already carrying "Issue Detected" status on Open Exchange. This
   reference implementation would be a *second* unofficial, single-session
   artifact in that same risk category — publishing it under InterSystems's
   name would misrepresent its support posture, and publishing it
   unofficially adds noise to a landscape the research explicitly says is
   already fragmented.

**What this reference implementation is actually good for:** a small,
honestly-tested example of what the read-only security boundary, row cap,
and timeout for an IRIS MCP tool should look like, and — this file's other
job — doing the schema-validation legwork (below) once, so whichever team
owns the AI Hub server's actual submission has already-validated manifest
shapes and a checklist to start from, instead of re-deriving both from
scratch.

## 1. MCP registry (`registry.modelcontextprotocol.io`)

**Schema used:** `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`
— fetched read-only in this session, saved at
`registry/mcp-registry/server.schema.json`, and used to validate
`registry/mcp-registry/server.json` with the real `jsonschema` PyPI package
(`scripts/validate_server_json.py`; result pasted in `STATUS.md`). This is
the exact `$schema` URL the registry's own docs use in
`docs/reference/server-json/generic-server-json.md` as of this session.

**Steps** (from `modelcontextprotocol.io/registry/quickstart` and the
registry repo's own docs, both found via search in this session — not fully
fetched, see `STATUS.md`):

1. Install the `mcp-publisher` CLI.
2. `mcp-publisher init` to scaffold `server.json` (this repo already has a
   hand-written one — start from that instead).
3. **Publish the actual package to a real package registry first.** The MCP
   registry stores metadata only, not artifacts — "you must publish the
   package to npm [or PyPI, etc.] before publishing the server to the MCP
   registry." For AI Hub's server this likely means whatever channel AI Hub
   already ships through (it ships *inside* IRIS 2026.x per
   `docs.intersystems.com` — `KEY=BAIHUB_mcp` — so the registry entry may
   need a `remotes` entry describing how to reach a running IRIS's `/mcp`
   endpoint, or a `packages` entry if AI Hub also ships a standalone
   installer/image; **decide this with the AI Hub team**, it is a product
   packaging question this session cannot answer).
4. `mcp-publisher login github` (or a domain-based login) to authenticate
   the namespace. **For an `io.github.intersystems-community/...` or
   `com.intersystems/...` name, this requires an InterSystems-controlled
   GitHub org login or DNS TXT record — neither exists in this session.**
5. `mcp-publisher publish path/to/server.json`.
6. Verify by searching the registry's own web UI for the published name.

**This session's `server.json` deliberately has no `packages`/`remotes`
entry** — see the file's own `_meta` note. Adding one here would either (a)
claim a PyPI/Docker identifier this session does not own (fails the
registry's package-ownership verification, and violates this task's own
rule against registering with any registry), or (b) require deciding AI
Hub's actual distribution channel, which is a product decision, not
something inferable from this repo. The `packages` entry to add once that's
decided, for the record:

```json
"packages": [{
  "registryType": "pypi",
  "registryBaseUrl": "https://pypi.org",
  "identifier": "<real-published-name>",
  "version": "<real-version>",
  "transport": { "type": "stdio" }
}]
```

## 2. Claude — two *different* mechanisms, don't conflate them

### 2a. Claude Desktop Extensions (MCPB, local install)

**Schema used:** the real JSON Schema shipped **inside** the official
`@anthropic-ai/mcpb` npm package (`schemas/mcpb-manifest-v0.4.schema.json`,
copied into `registry/claude-desktop-extension/` in this repo) — not a
hand-derived approximation. Validated with the actual `mcpb` CLI
(`npx @anthropic-ai/mcpb validate manifest.json`); result pasted in
`STATUS.md`.

**Steps:**

1. `npm install -g @anthropic-ai/mcpb` (or `npx`).
2. `mcpb validate manifest.json` — already done in this repo, passes.
3. Package: `mcpb pack <directory> <output>.mcpb` (bundles the server +
   manifest into a distributable file). **Not done here** — packing
   correctly requires deciding whether AI Hub's server is distributed as a
   `python`/`node`/`binary`/`uv` MCPB type, which depends on how/whether it
   is meant to run *outside* an IRIS instance at all (AI Hub's server is an
   IRIS-hosted HTTP endpoint, not a local stdio process someone's desktop
   would spawn — **this raises a real question about whether MCPB is even
   the right mechanism for AI Hub's server**, vs. the remote-connector path
   in 2b, which fits an HTTP endpoint much better).
4. Submit via Anthropic's **desktop-extension submission form**
   (`clau.de/desktop-extention-submission`, a Google Form — found via
   search in this session, not fetched/filled). Missing/incomplete privacy
   policy is stated to cause immediate rejection; every tool needs correct
   read-only/destructive annotations (this repo's tools already have them —
   see `server.py`'s `_READ_ONLY` `ToolAnnotations`).

### 2b. Claude Connectors Directory (claude.ai, remote MCP servers)

This is the one that actually fits AI Hub's server, which is already an
HTTP-reachable IRIS endpoint.

**No downloadable schema — it's a web form**, per
`claude.com/docs/connectors/building/submission` (search snippets only in
this session; direct fetch was `EGRESS_BLOCKED`). Documented requirements:

- **Org tier:** Team or Enterprise Claude.ai organization, with "Directory"
  or "Libraries" permission.
- **Transport:** Streamable HTTP required; **SSE is no longer accepted.**
- **Auth:** OAuth 2.0 with a real user-consent flow.
- **Form sections:** server basics (name, tagline, server URL, connector
  type), connection details, tools & resources (every tool needs a
  human-readable title and confirmed read-only/destructive annotations —
  the two things the docs say "decide most submissions"), documentation
  (public docs URL + at least 3 example prompts), and a public privacy
  policy (missing one is an immediate rejection).
- **Test-account access** detailed enough for an Anthropic reviewer to
  exercise every tool themselves.
- Enters the directory first as a **community connector**; Anthropic may
  later select it for a higher-touch **verified** review.

**Human actions InterSystems needs to complete this, that no code change
can substitute for:** a Team/Enterprise Claude.ai org with directory
permission, AI Hub's server actually reachable over Streamable HTTP with
OAuth in front of it (confirm with the AI Hub team whether IRIS 2026.x's
`iris-mcp-server` already speaks Streamable HTTP or currently only SSE/stdio
— this session could not check, no IRIS instance available), a public
privacy policy URL, and a reviewer-usable test account against a real IRIS
namespace.

## 3. ChatGPT / OpenAI Apps SDK connector directory

**No public, fetchable manifest schema exists.** See
`registry/chatgpt/README.md` for the full explanation and citations. In
short: legacy ChatGPT plugins used a `/.well-known/ai-plugin.json` file;
that's superseded by the Apps SDK / MCP-based flow, which has **no
equivalent standalone manifest file** — the MCP server itself plus a portal
submission is the whole artifact.

**Steps** (from search snippets against `developers.openai.com/apps-sdk/*`
and `.../plugins/deploy/*`; direct fetch of that domain was
`EGRESS_BLOCKED` in this session):

1. Get an org role with "Apps Management: Write" in the OpenAI developer
   platform.
2. Create a plugin draft in the submission portal: MCP server URL, listing
   metadata (name/subtitle/description/category/logo/URLs), auth mode.
3. **Domain verification** for whatever host serves the MCP endpoint.
4. Provide tool justifications and reviewer test access; the server must
   already support representative inputs, edge cases, and empty results
   cleanly.
5. After approval, explicitly **publish** from the portal — approval alone
   doesn't list it.
6. "Enhanced distribution" (featured placement) is reviewer-selected, not
   requestable.

`registry/chatgpt/submission_prep.json` in this repo is this session's own
draft of the listing fields above, explicitly labeled as not
schema-validated, so whoever has portal access doesn't start from a blank
form — see that file's `_disclaimer` field.

**Human actions required, same shape as 2b:** a hosted Streamable-HTTP
endpoint for AI Hub's server, domain ownership/verification for that host,
an OpenAI developer-org account with the right permission, and a review
SLA that is entirely OpenAI's to set (not found/estimated in this session —
flagged rather than guessed).

## Summary table

| Directory | Manifest/schema status | What's missing to actually submit |
| --- | --- | --- |
| MCP registry | Real schema fetched + validated (`server.json` passes) | Real published package/remote entry; InterSystems GitHub/domain auth for the namespace |
| Claude Desktop Extensions (MCPB) | Real schema (shipped in `@anthropic-ai/mcpb`) + validated via the real CLI | Decision on whether MCPB (local) even fits AI Hub's server; privacy policy; form submission |
| Claude Connectors Directory (remote) | No schema — web form (documented fields captured above) | Team/Enterprise org; Streamable HTTP + OAuth confirmed on AI Hub's server; privacy policy; reviewer test access |
| ChatGPT / Apps SDK | No schema at all — portal + hosted server is the whole artifact | Public HTTPS endpoint + domain verification; developer-org account; portal submission |

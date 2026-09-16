# ChatGPT connector directory — no fetchable manifest schema exists

This directory intentionally does **not** contain a `manifest.json` or any
other file claiming to be "the ChatGPT connector manifest," because that
artifact does not exist as a standalone, publicly fetchable, schema-checkable
file. This was confirmed by search against OpenAI's own developer docs
(`developers.openai.com/apps-sdk/*`); the docs domain itself returned
`EGRESS_BLOCKED` when fetched directly in this sandbox, so the claims below
are from the search-result snippets of those pages, not a full fetch --
flagged as such, and re-flagged in `STATUS.md`.

## What actually gates a ChatGPT/Apps SDK submission

1. **The MCP server itself**, reachable over HTTPS at a public `/mcp`
   endpoint (Streamable HTTP). There is no separate discovery manifest file
   analogous to the old ChatGPT-plugin-era `/.well-known/ai-plugin.json` --
   that legacy plugin format is superseded by the Apps SDK / MCP-based
   submission flow.
2. **A developer-portal submission** (per
   `developers.openai.com/apps-sdk/app-submission-guidelines` and
   `.../plugins/deploy/submission`): the org account needs "Apps Management:
   Write" permission, then a plugin draft is created in the portal with:
   - Public listing metadata: name, subtitle, description, category, logo,
     supporting URLs.
   - The MCP server URL itself.
   - **Domain verification** proving control of the domain hosting the
     server.
   - Tool justifications / review materials for each tool exposed.
3. **Review**, then an explicit publish step from the portal before the
   listing appears in the universal plugin/app directory. "Enhanced
   distribution" (featured placement) is reviewer-selected, not
   requestable.

None of this is a JSON document you author offline and hand-validate the way
`server.json` (MCP registry) or `manifest.json` (MCPB/Claude Desktop
Extension) can be. It is an authenticated, hosted-endpoint, domain-verified
workflow that cannot be completed, or even meaningfully staged, from this
sandbox: there is no OpenAI developer-org account here, no public HTTPS
endpoint for this reference server (it is stdio-only by design -- see
README.md), and no domain to verify.

## What this directory provides instead

`submission_prep.json` -- **not a schema, not validated against anything,
labeled as such in the file itself** -- is this session's own organization
of the listing fields the portal is documented to ask for, filled in with
what we know about this project, so that whoever does have the
InterSystems developer-portal access does not have to start from a blank
form. It is a checklist artifact, not a submission artifact.

It also isn't the recommended path anyway: see `PUBLISHING.md` in the
package root for why the call is to submit AI Hub's own `iris-mcp-server`
(which is an HTTP-reachable, InterSystems-owned server) rather than this
stdio-only reference implementation, which structurally cannot satisfy
ChatGPT's "public HTTPS `/mcp` endpoint" requirement without first being
deployed as a hosted service by someone who can also complete domain
verification for it.

# iris-ai-examples

Working AI Hub applications built on InterSystems IRIS — ready to run, domain-specific, and built for demonstration.

Three of the examples ship a Docker stack, seeded demo data, and a set of MCP tools you can drive from Claude Desktop, VS Code, or any MCP client. `ai-hub/` is a pattern library you read and copy from rather than a stack you start. `ai-hub-service/` turns AI Hub into a deployable service (REST in front, agents and governance inside) and proves it on CareConnect.

## Examples

| Example                                     | Domain                     | Language                       | Tools              | AI Hub APIs                                                            | Interop                                                   |
| ------------------------------------------- | -------------------------- | ------------------------------ | ------------------ | ---------------------------------------------------------------------- | --------------------------------------------------------- |
| [careconnect-sdoh](./careconnect-sdoh/)     | Healthcare / SDoH          | ObjectScript                   | 18                 | `%AI.ToolSet`, `%AI.MCP.Service`                                       | BS → BP → BO production                                   |
| [careconnect-python](./careconnect-python/) | Healthcare / SDoH          | Python (`iris_llm`)            | 4                  | `iris_llm.Agent`, `@tool`                                              | —                                                         |
| [kg-ticket-resolver](./kg-ticket-resolver/) | Support / Knowledge Mining | ObjectScript                   | 6                  | `%AI.ToolSet`, `%AI.MCP.Service`, `%AI.Agent`, `%AI.Provider`          | —                                                         |
| [ai-hub](./ai-hub/)                         | Patterns library           | Both                           | —                  | OTel, ConfigStore, Bridge, Jira MCP, Interop+OTel, Python `@tool`      | OTel Interop spans                                        |
| [ai-hub-service](./ai-hub-service/)         | Agents as a service        | Python + ObjectScript wrappers | 10 (CareConnect's) | `%AI.MCP.Service` behind a REST contract; any IRIS version as a caller | Agents as a business operation; drives legacy productions |

The two CareConnect examples solve the same problem in the two supported languages. Read
them side by side to see what the ObjectScript and Python SDKs each cost you.

### [`careconnect-sdoh/`](./careconnect-sdoh/)

#### Healthcare SDoH Assessment Agent

A community health worker assistant that assesses Social Determinants of Health for patients and triggers follow-up workflows through IRIS Interoperability.

- 18 MCP tools: 11 core (including a Liquid d1 decision gate for follow-up actions) and 7 knowledge-graph tools that need the `--profile ivg` stack
- IRIS Interoperability production wired end-to-end (BusinessService → BusinessProcess → BusinessOperation)
- 3 pre-seeded demo patients covering diabetes/hypertension, CHF/depression, and prenatal care
- Shows how an agent can observe and trigger production workflows — not just query data

**Best for demonstrating:** `%AI.ToolSet`, `%AI.MCP.Service`, IRIS Interoperability integration with AI agents, Ens.Director, live message tracing, and **agent evaluation** — a provider-agnostic eval suite ([`evals/`](./careconnect-sdoh/evals/)) scoring trajectory, outcome, deterministic regression, and LLM-as-judge across a golden patient set

---

### [`careconnect-python/`](./careconnect-python/)

#### The same SDoH agent, written in Python

`careconnect-sdoh` in Python, using the `iris_llm` SDK instead of `%AI.ToolSet`. Tools are
plain functions with an `@tool` decorator; the agent loop is `iris_llm.Agent`. No
ObjectScript.

- 4 tools: patient roster, SDoH risk assessment, community-resource lookup, findings summary
- `iris_llm.Agent` drives the loop; `iris.connect()` (DBAPI) reads the same demo tables
- The wheel ships inside the IRIS image at `/usr/irissys/dev/python/` — nothing to publish
- Runs as an ordinary Python process against IRIS, so it fits existing Python codebases

**Best for demonstrating:** the Python SDK, the `@tool` decorator, and what a team gives up
(Interoperability, in-database execution) by staying outside ObjectScript

---

### [`kg-ticket-resolver/`](./kg-ticket-resolver/)

#### Support Ticket Knowledge Mining Agent

A support engineer assistant that mines a backlog of 276 synthetic EMR support tickets, scores data completeness, finds similar tickets via vector search, and drafts KB articles using a `%AI.Agent` running inside IRIS.

- 6 MCP tools: MDS completeness scoring, semantic vector search (IRIS `VECTOR_COSINE`), cluster analysis, AI-generated KB articles, wiki management with Graph_KG provenance
- `%AI.Agent` + `%AI.Provider` pattern: an agent running inside IRIS called via MCP
- IRIS native vector search (`VECTOR(DOUBLE, 384)` + `VECTOR_COSINE`) — no external vector DB
- Jupyter notebooks showing the same pipeline from a data science perspective
- Pre-existing wiki with documented knowledge gaps, augmented by the agent

**Best for demonstrating:** `%AI.Agent` + `%AI.Provider`, IRIS native vector search, MDS scoring, knowledge graph provenance, agentic KB synthesis, notebook-friendly architecture

---

### [`ai-hub/`](./ai-hub/)

#### AI Hub Pattern Library

Reference patterns covering production concerns not in the core EAP sample library:
OTel observability, ConfigStore governance, Python bridge governance, external MCP
servers (Atlassian Rovo), and IRIS Interoperability + OTel integration.

- **OTel observability**: gen_ai.\* semantic convention spans, W3C traceparent
  propagation, pre-generated chat span IDs so tool-call spans are children
- **ConfigStore governance**: provider credentials + model via IRIS RBAC — no
  hardcoded env-var secrets
- **Python bridge governance**: `@tool` functions governed by deny/allow-list
  `%AI.Policy`, exposed as `%AI.MCP.Service` endpoint
- **Jira / Atlassian MCP**: `%AI.ToolSet` pointing at the official Atlassian
  Rovo MCP Server with bearer auth
- **Interop + OTel**: BS/BP/BO all emitting gen_ai.\* spans into a shared trace

**Best for demonstrating:** production governance patterns, OTel observability,
embedded Python (`irispython`), `iris_tool_bridge`, IRIS Interoperability + AI tracing

---

### [`ai-hub-service/`](./ai-hub-service/)

#### AI Hub as a service: agents over REST, for any IRIS

A service in a box for teams that want to call agents from the ObjectScript, SQL and
Interoperability code they already have, on the IRIS version they already run, without
adopting an SDK. It is a REST service with a tool catalog, an agent runtime, and a
governance layer, deployable with `kubectl apply -k`.

- Three topologies, one config each: **in-place** (in front of an AI Hub IRIS),
  **sidecar** (a legacy IRIS keeps its data and production, an AI Hub companion runs the
  `%AI` logic, and the service meshes them per tool), and **offline**
- Human approval enforced by the runtime: a `write` tool parks the run until an approver
  decides, whatever the model wanted
- Deterministic playbook agents alongside OpenAI-compatible and Anthropic model loops
- Version-neutral ObjectScript wrappers: `SELECT AIHub.Ask(...)`, an Interop business
  operation, a client class, and an allow-listed dispatcher for legacy productions
- CareConnect's SDoH agent gives the same answer in all three topologies, pinned by tests
  that need no Docker and no key

**Best for demonstrating:** what AI Hub looks like to a customer who asked for a service
rather than an SDK. [DESIGN.md](./ai-hub-service/DESIGN.md) is the argument and is
explicit about what is not yet verified.

---

## Requirements

- InterSystems IRIS AI Hub, community image `irishealth-community:2026.2.0AI.162.0` or later
  - Download: [evaluation.intersystems.com/Eval/early-access/AIHub](https://evaluation.intersystems.com/Eval/early-access/AIHub)
  - This is the one version number that matters. Where an example's own README names a
    higher build, it is calling out a feature added later — the example still runs on 162.
- Docker + Docker Compose
- An MCP client: Claude Desktop, VS Code with Copilot, or any MCP-compatible tool
- An OpenAI API key, but only for the tools that call a model — `DraftKBArticle` in
  `kg-ticket-resolver/`, the `%AI.Agent` samples in `ai-hub/`, and `careconnect-python/`.
  Every other tool in every example is rule-based and runs without one.

### One API-key idiom

Each example reads the key from `OPENAI_API_KEY` in the process environment, seeded from
its own `.env`. That is the quickstart path, and it is the only one the examples require.

For anything past a demo, put the key in the IRIS ConfigStore instead and let the provider
resolve it: an `%AI.Provider` config holds `"api_key": "@{env:OPENAI_API_KEY}"` or a
`@{wallet:...}` reference, so the secret is governed by IRIS RBAC rather than readable in
`docker inspect`. The worked pattern is
`ai-hub/objectscript/cls/Sample/AI/Examples/ConfigStoreSetup.cls` plus
`ConfigStoreAgent.cls`: `%ConfigStore.Configuration.Create` for the entry, then a provider
that reads it by name. Use the environment variable to get running; move to ConfigStore
before anyone else can read the container.

## AI Hub Concepts Covered

| Concept                                                                  | Where demonstrated                                       |
| ------------------------------------------------------------------------ | -------------------------------------------------------- |
| `%AI.ToolSet` — define tools in ObjectScript XData                       | careconnect-sdoh, kg-ticket-resolver, ai-hub             |
| `%AI.MCP.Service` — expose a ToolSet via MCP endpoint                    | careconnect-sdoh, kg-ticket-resolver, ai-hub             |
| `iris-mcp-server` — connect any MCP client to IRIS                       | careconnect-sdoh, kg-ticket-resolver                     |
| `%AI.Agent` — run an LLM agent loop inside IRIS                          | kg-ticket-resolver: `DraftKBArticle`                     |
| `%AI.Provider` — configure LLM backends                                  | kg-ticket-resolver: `DraftKBArticle`                     |
| `iris_llm.Agent` + `@tool` — the Python SDK                              | careconnect-python; ai-hub bridge pattern                |
| IRIS Interoperability + AI — trigger BS/BP/BO from an agent tool         | careconnect-sdoh                                         |
| IRIS native vector search — `VECTOR` type + `VECTOR_COSINE`              | kg-ticket-resolver: `FindSimilarTickets`                 |
| Graph_KG provenance — record agent actions as graph edges                | kg-ticket-resolver: `PublishKBArticle`                   |
| Knowledge-graph tools + contradiction gating                             | careconnect-sdoh (`--profile ivg`)                       |
| OTel observability — `gen_ai.*` spans, W3C traceparent                   | ai-hub                                                   |
| ConfigStore governance — credentials via IRIS RBAC, not env vars         | ai-hub                                                   |
| OAuth 2.0 + role-filtered tool catalogs                                  | ai-hub: `Sample.AI.OAuth`                                |
| Demo data seeding — idempotent `%Persistent` table population            | careconnect-sdoh, careconnect-python, kg-ticket-resolver |
| MCP sidecar pattern — `iris-mcp-server` alongside IRIS in Docker Compose | careconnect-sdoh, kg-ticket-resolver                     |

## Running an Example

Each example is self-contained, but they do not all start the same way. Start from the
example's own README; the table below is the short version.

| Example              | How to start it                                                                                                                     |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `careconnect-sdoh`   | `make up` (or `docker compose up -d --wait`) from the example root                                                                  |
| `careconnect-python` | `cd docker && docker compose up -d iris`, then `docker compose run agent python agent.py "…"`                                       |
| `kg-ticket-resolver` | `cd docker && docker compose up -d`                                                                                                 |
| `ai-hub`             | No stack. Load the classes you want into an existing AI Hub instance.                                                               |
| `ai-hub-service`     | `python -m aihub_service --config examples/careconnect/offline.yaml`, or `docker compose --profile offline\|inplace\|sidecar up -d` |

For the three Docker examples, connect your MCP client to the running server afterwards —
each README carries the exact client config.

## Documentation

Start from the example's own README. Everything else is listed here, so no doc in this
repo is reachable only by listing the files.

| Doc                                                                         | What it covers                                                                          |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **careconnect-sdoh**                                                        |                                                                                         |
| [README](./careconnect-sdoh/README.md)                                      | Quickstart, the 18 tools, MCP client config, architecture                               |
| [DEMO.md](./careconnect-sdoh/DEMO.md)                                       | 10-minute walkthrough: one health worker, one patient, tool call by tool call           |
| [docs/eap-setup.md](./careconnect-sdoh/docs/eap-setup.md)                   | Getting the AI Hub EAP image, and what still runs without it                            |
| [evals/README](./careconnect-sdoh/evals/README.md)                          | Running the eval suite — offline, no API key, under a second                            |
| [evals/EVALS.md](./careconnect-sdoh/evals/EVALS.md)                         | The five evaluation layers, and the three defects the suite finds in the shipped tools  |
| [evals/PRESENTATION.md](./careconnect-sdoh/evals/PRESENTATION.md)           | 15–20 minute talk track for presenting the eval suite                                   |
| **careconnect-python**                                                      |                                                                                         |
| [README](./careconnect-python/README.md)                                    | Quickstart, the `@tool` pattern, what Python costs you against the ObjectScript version |
| [DEMO.md](./careconnect-python/DEMO.md)                                     | The same SDoH session, driven from an ordinary Python process                           |
| **kg-ticket-resolver**                                                      |                                                                                         |
| [README](./kg-ticket-resolver/README.md)                                    | Quickstart, the 6 tools, vector search and graph provenance                             |
| [DEMO.md](./kg-ticket-resolver/DEMO.md)                                     | 15-minute walkthrough: 276 tickets to a published KB article                            |
| [data/planetcare_wiki](./kg-ticket-resolver/data/planetcare_wiki/README.md) | The seeded wiki the agent mines, and the gaps it is meant to fill                       |
| **ai-hub**                                                                  |                                                                                         |
| [README](./ai-hub/README.md)                                                | The pattern library: OTel, ConfigStore, bridge governance, Jira MCP, Interop spans      |
| [Sample.AI.OAuth](./ai-hub/objectscript/cls/Sample/AI/OAuth/README.md)      | Bearer token to IRIS roles to a role-filtered tool catalog, with the measured matrix    |
| [fixtures/keycloak](./ai-hub/fixtures/keycloak/README.md)                   | The throwaway IdP those measurements came from                                          |
| **ai-hub-service**                                                          |                                                                                         |
| [README](./ai-hub-service/README.md)                                        | Quickstart, the approval walkthrough, the three modes, Kubernetes, calling it from IRIS |
| [DESIGN.md](./ai-hub-service/DESIGN.md)                                     | Why a service, the topologies, meshing options weighed, governance, what is unverified  |
| **Repo-wide**                                                               |                                                                                         |
| [AGENTS.md](./AGENTS.md)                                                    | Project index and build commands, written for coding agents                             |
| [CLAUDE.md](./CLAUDE.md)                                                    | Claude Code's instructions for this repo                                                |
| [skills/iris-ai-examples](./skills/iris-ai-examples/SKILL.md)               | This repo packaged as a Claude skill                                                    |

`pytest tests/` fails if a doc is added without a link here, or if a relative link in any
doc stops resolving.

## Related

- [ready-hackathon-dev-template](https://github.com/intersystems-community/ready-hackathon-dev-template) — minimal starter if you're building something new
- [iris-vector-graph](https://github.com/intersystems-community/iris-vector-graph) — graph + vector engine for more advanced RAG patterns
- [ready2026-knowledge-graph-demo](https://github.com/intersystems-community/ready2026-knowledge-graph-demo) — standalone notebook version of the ticket mining pipeline

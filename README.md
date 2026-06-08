# iris-ai-examples

Working AI Hub applications built on InterSystems IRIS — ready to run, domain-specific, and built for demonstration.

Each example ships with a Docker stack, seeded demo data, and a set of MCP tools you can drive from Claude Desktop, VS Code, or any MCP client. No configuration required beyond an API key.

## Examples

| Example | Domain | Tools | AI Hub APIs | Interop |
|---------|--------|-------|-------------|---------|
| [careconnect-sdoh](./careconnect-sdoh/) | Healthcare / SDoH | 9 | `%AI.ToolSet`, `%AI.MCP.Service` | BS → BP → BO production |
| [kg-ticket-resolver](./kg-ticket-resolver/) | Support / Knowledge Mining | 6 | `%AI.ToolSet`, `%AI.MCP.Service`, `%AI.Agent`, `%AI.Provider` | — |

### [`careconnect-sdoh/`](./careconnect-sdoh/)

**Healthcare SDoH Assessment Agent**

A community health worker assistant that assesses Social Determinants of Health for patients and triggers follow-up workflows through IRIS Interoperability.

- 9 MCP tools: patient lookup, SDoH risk scoring across 5 USDHHS domains, care plan generation, follow-up workflow trigger, interop message tracing
- IRIS Interoperability production wired end-to-end (BusinessService → BusinessProcess → BusinessOperation)
- 3 pre-seeded demo patients covering diabetes/hypertension, CHF/depression, and prenatal care
- Shows how an agent can observe and trigger production workflows — not just query data

**Best for demonstrating:** `%AI.ToolSet`, `%AI.MCP.Service`, IRIS Interoperability integration with AI agents, Ens.Director, live message tracing, and **agent evaluation** — a provider-agnostic eval suite ([`evals/`](./careconnect-sdoh/evals/)) scoring trajectory, outcome, deterministic regression, and LLM-as-judge across a golden patient set

---

### [`kg-ticket-resolver/`](./kg-ticket-resolver/)

**Support Ticket Knowledge Mining Agent**

A support engineer assistant that mines a backlog of 276 synthetic EMR support tickets, scores data completeness, finds similar tickets via vector search, and drafts KB articles using a `%AI.Agent` running inside IRIS.

- 6 MCP tools: MDS completeness scoring, semantic vector search (IRIS `VECTOR_COSINE`), cluster analysis, AI-generated KB articles, wiki management with Graph_KG provenance
- `%AI.Agent` + `%AI.Provider` pattern: an agent running inside IRIS called via MCP
- IRIS native vector search (`VECTOR(DOUBLE, 384)` + `VECTOR_COSINE`) — no external vector DB
- Jupyter notebooks showing the same pipeline from a data science perspective
- Pre-existing wiki with documented knowledge gaps, augmented by the agent

**Best for demonstrating:** `%AI.Agent` + `%AI.Provider`, IRIS native vector search, MDS scoring, knowledge graph provenance, agentic KB synthesis, notebook-friendly architecture

---

## Requirements

- InterSystems IRIS AI Hub community build 162+
  - Download: [evaluation.intersystems.com/Eval/early-access/AIHub](https://evaluation.intersystems.com/Eval/early-access/AIHub)
- Docker + Docker Compose
- An MCP client: Claude Desktop, VS Code with Copilot, or any MCP-compatible tool
- OpenAI API key (for `DraftKBArticle` and `%AI.Agent` tools — other tools work without one)

## AI Hub Concepts Covered

| Concept | Where demonstrated |
|---------|-------------------|
| `%AI.ToolSet` — define tools in ObjectScript XData | Both examples |
| `%AI.MCP.Service` — expose a ToolSet via MCP endpoint | Both examples |
| `iris-mcp-server` — connect any MCP client to IRIS | Both examples |
| `%AI.Agent` — run an LLM agent loop inside IRIS | kg-ticket-resolver: `DraftKBArticle` |
| `%AI.Provider` — configure LLM backends | kg-ticket-resolver: `DraftKBArticle` |
| IRIS Interoperability + AI — trigger BS/BP/BO from an agent tool | careconnect-sdoh |
| IRIS native vector search — `VECTOR` type + `VECTOR_COSINE` | kg-ticket-resolver: `FindSimilarTickets` |
| Graph_KG provenance — record agent actions as graph edges | kg-ticket-resolver: `PublishKBArticle` |
| Demo data seeding — idempotent `%Persistent` table population | Both examples |
| MCP sidecar pattern — `iris-mcp-server` alongside IRIS in Docker Compose | Both examples |

## Running an Example

Each example is self-contained. From any example directory:

```bash
cd <example>/docker
docker compose up -d
```

Then connect your MCP client to the running server. See each example's README for the exact client config.

## Related

- [ready-hackathon-dev-template](https://github.com/intersystems-community/ready-hackathon-dev-template) — minimal starter if you're building something new
- [iris-vector-graph](https://github.com/intersystems-community/iris-vector-graph) — graph + vector engine for more advanced RAG patterns
- [ready2026-knowledge-graph-demo](https://github.com/intersystems-community/ready2026-knowledge-graph-demo) — standalone notebook version of the ticket mining pipeline

# iris-ai-examples

Real-world AI Hub applications built on InterSystems IRIS.

These are working, domain-specific examples — not starter templates. Each demonstrates a complete AI Hub pattern using `%AI.Agent`, `%AI.ToolSet`, MCP tools, and IRIS capabilities.

## Examples

### [`careconnect-sdoh/`](./careconnect-sdoh/)

**Healthcare SDoH Assessment Agent**

A community health worker assistant that assesses Social Determinants of Health (SDoH) for patients using IRIS AI Hub MCP tools and an IRIS Interoperability production.

- 9 MCP tools: patient lookup, SDoH risk scoring, care plan generation, follow-up workflow
- IRIS Interoperability production (BusinessService → BusinessProcess → BusinessOperation)
- Live message traces via `GetInteropTraces`
- 3 demo patients (diabetes, CHF, prenatal care) seeded automatically

**What it shows:** `%AI.MCP.Service`, `%AI.ToolSet`, Interop BS/BP/BO wired to MCP, `Ens.Director`, demo data seeding via `%Persistent`

---

### [`kg-ticket-resolver/`](./kg-ticket-resolver/)

**Support Ticket Knowledge Mining Agent**

A support engineer assistant that mines a backlog of EMR support tickets, scores completeness, finds similar tickets via semantic search, and drafts KB articles using an AI Hub agent. Uses [iris-vector-graph](https://github.com/intersystems-community/iris-vector-graph) for hybrid vector + graph retrieval.

- 6 MCP tools: MDS scoring, semantic search, cluster analysis, KB article generation, wiki management
- `%AI.Agent` running inside IRIS for KB article synthesis
- iris-vector-graph `kg_NodeEmbeddings` for semantic ticket search
- Graph_KG provenance: `AUTHORED_KB` / `SOURCED_KB` edges trace every article to source tickets
- Pre-existing wiki with documented knowledge gaps, augmented by the agent
- Jupyter notebooks for data science exploration of the same pipeline

**What it shows:** `%AI.Agent` + `%AI.Provider`, `%AI.ToolSet`, iris-vector-graph semantic search, Graph_KG provenance, MDS completeness scoring, wiki augmentation pattern
- More examples at [intersystems-community](https://github.com/intersystems-community)

## Requirements

- InterSystems IRIS AI Hub build 162+ (community edition)
  - Download: [evaluation.intersystems.com/Eval/early-access/AIHub](https://evaluation.intersystems.com/Eval/early-access/AIHub)
- Docker + Docker Compose
- An MCP client: Claude Desktop, VS Code, or any MCP-compatible tool

## Related

- [ready-hackathon-dev-template](https://github.com/intersystems-community/ready-hackathon-dev-template) — Start here if you're new to AI Hub
- [iris-vector-graph](https://github.com/intersystems-community/iris-vector-graph) — Knowledge graph engine used by these examples

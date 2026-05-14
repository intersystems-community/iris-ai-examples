# KG Ticket Resolver — AI Hub Example

A support ticket knowledge mining agent built on InterSystems IRIS AI Hub.

Ask Claude: *"How complete is ticket PC-00145? Find similar billing tickets and draft a KB article."*

Claude calls 6 MCP tools backed by IRIS — scoring ticket quality, finding related tickets via vector search, generating a KB article using a `%AI.Agent` running inside IRIS, and publishing it to a wiki with full provenance in the knowledge graph.

## Quickstart

### 1. Get the AI Hub image

Download `irishealth-community-2026.2.0AI.162.0-docker.tar.gz` from:
https://evaluation.intersystems.com/Eval/early-access/AIHub

```bash
docker load < irishealth-community-2026.2.0AI.162.0-docker.tar.gz
```

### 2. Start the stack

```bash
export OPENAI_API_KEY=sk-...   # required for DraftKBArticle; other tools work without it
cd docker
docker compose up -d
```

Wait ~2 minutes. IRIS initializes, loads 276 demo tickets, and registers 6 MCP tools.

### 3. Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kgtickets": {
      "command": "docker",
      "args": [
        "exec", "-i", "kgtickets-mcp",
        "/usr/irissys/bin/iris-mcp-server",
        "run",
        "--iris-host", "localhost",
        "--iris-port", "52773",
        "--iris-user", "_SYSTEM",
        "--iris-password", "SYS",
        "--iris-endpoint", "/mcp/kgtickets"
      ]
    }
  }
}
```

Restart Claude Desktop. The `kgtickets` server appears with 6 tools.

### 4. Demo script

**Step through with Claude:**

```
"What's the MDS completeness score for ticket PC-00001?"

"Find tickets similar to 'invoice amount mismatch after system upgrade'"

"Show me the cluster summary for BILLING — how many are resolved?"

"What's the current wiki status? Which categories have gaps?"

"Draft a KB article for the BILLING cluster"

"Publish that article to the wiki"
```

**Or ask Claude to run the full pipeline:**
```
"Score PC-00145, find similar pharmacy tickets, and draft and publish a KB article for PHARMACY"
```

## Tools

| Tool | What it does |
|------|-------------|
| `ScoreTicketCompleteness` | MDS score (0–100) and tier (HIGH/MEDIUM/LOW) for a ticket — has it enough data to generate KB content? |
| `FindSimilarTickets` | Semantic vector search (IRIS `VECTOR_COSINE`) across 276 tickets. Falls back to keyword if embeddings not seeded. |
| `GetClusterSummary` | Resolution statistics and anchor tickets for a category — shows what the agent knows about a problem space |
| `DraftKBArticle` | Calls a `%AI.Agent` inside IRIS to synthesize a structured KB article from resolved tickets (**requires OPENAI_API_KEY**) |
| `GetWikiStatus` | Lists existing wiki files and shows resolution coverage by category |
| `PublishKBArticle` | Writes approved article to `data/planetcare_wiki/` and records `AUTHORED_KB` / `SOURCED_KB` edges in Graph_KG |

## What it demonstrates

- **`%AI.Agent` + `%AI.Provider`** — an LLM agent loop running inside IRIS, not called from Python. `DraftKBArticle` creates a provider, agent, session, and calls `agent.Chat()` — all in ObjectScript
- **`%AI.ToolSet`** — 6 domain-specific tools defined in XData, compiled into IRIS, discoverable by `iris-mcp-server`
- **`%AI.MCP.Service`** — the ToolSet exposed on `/mcp/kgtickets` via the IRIS web server
- **IRIS native vector search** — `SummaryVec VECTOR(DOUBLE, 384)` stored on the ticket table; `VECTOR_COSINE` queries it — no external vector database
- **Graph_KG provenance** — `PublishKBArticle` writes `AUTHORED_KB` and `SOURCED_KB` edges into `Graph_KG.rdf_edges`, creating a traceable audit trail
- **MDS scoring** — `ScoreTicketCompleteness` gates KB generation: only tickets with problem + solution text produce high-quality articles
- **MCP sidecar pattern** — `iris-mcp-server` runs alongside IRIS in Docker Compose, sharing the network

## Architecture

```
Claude Desktop / VS Code
    │
    │  MCP (stdio via docker exec)
    ▼
iris-mcp-server  (kgtickets-mcp container, shares network with iris)
    │
    │  HTTP to IRIS web server :52773
    ▼
KGTicketResolver.MCP.Service  (%AI.MCP.Service at /mcp/kgtickets)
    │
    ▼
KGTicketResolver.Tools.ToolSet  (%AI.ToolSet)
    ├── ScoreTicketCompleteness   ← SQL on KGTicketResolver_Ticket.Record
    ├── FindSimilarTickets        ← VECTOR_COSINE(SummaryVec, query_vec) or keyword fallback
    ├── GetClusterSummary         ← SQL aggregates + anchor ticket extraction
    ├── DraftKBArticle            ← %AI.Agent + %AI.Provider("openai") running inside IRIS
    ├── GetWikiStatus             ← filesystem check + SQL coverage summary
    └── PublishKBArticle          ← file write to /app/wiki/ + Graph_KG.rdf_edges INSERT
```

## Demo data

All data is synthetic — no real patient data, no real hospital names.

| File | Contents |
|------|----------|
| `data/planetcare_demo_tickets.json` | 276 synthetic PlanetCare EMR tickets · 7 categories · ~42% resolved |
| `data/planetcare_wiki/` | 3 pre-existing KB stubs with documented gaps (billing, laboratory, pharmacy) |
| `data/questionnaire_clusters_anon.csv` | 295 anonymized questionnaire tickets with HDBSCAN cluster labels (for notebooks) |

**Ticket categories:** BILLING, LABORATORY, PHARMACY, PRINTING, INTERFACING, WAITING_LISTS, QUESTIONNAIRES

## Vector search

`FindSimilarTickets` uses IRIS native vector search when embeddings are available:

```sql
SELECT TOP 8 TicketId, Category, Summary,
       VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE)) sim
FROM KGTicketResolver_Ticket.Record
WHERE SummaryVec IS NOT NULL
ORDER BY sim DESC
```

Embeddings are optional. Without them, the tool falls back to keyword matching. To seed embeddings, run the optional notebook cell in `planetcare_clustering_demo.ipynb` — it embeds all 276 tickets using local `all-MiniLM-L6-v2` (no API key needed).

## Knowledge graph provenance

Every article published by the agent is recorded in Graph_KG. Query it with:

```sql
SELECT s, p, o_id FROM Graph_KG.rdf_edges
WHERE s LIKE 'kb_article:%' OR o_id LIKE 'kb_article:%'
```

Or in Cypher (via iris-vector-graph):

```cypher
MATCH (agent)-[:AUTHORED_KB]->(kb)<-[:SOURCED_KB]-(ticket)
RETURN agent, kb.article_id, ticket.ticket_id
LIMIT 20
```

## Jupyter notebooks

For data science exploration of the same pipeline:

```bash
pip install -r requirements.txt
export IRIS_CONTAINER=kgtickets-iris   # matches docker-compose container name
jupyter notebook notebooks/
```

| Notebook | What it shows |
|----------|--------------|
| `planetcare_clustering_demo.ipynb` | MDS gap analysis → HDBSCAN clustering → MDS agent gates pipeline → AI Hub KB synthesis (Writer → Reviewer → Publisher) |
| `planetcare_system_demo.ipynb` | IRIS vector search API, `VECTOR_COSINE`, SQL and graph queries |

## Source layout

```
kg-ticket-resolver/
├── docker/
│   ├── docker-compose.yml    Two services: iris (full stack) + mcp (sidecar)
│   ├── Dockerfile            Builds IRIS image with classes compiled + data seeded
│   └── iris.script           Compiles classes, seeds 276 tickets, registers MCP tools
├── src/KGTicketResolver/
│   ├── Tools/ToolSet.cls     %AI.ToolSet — all 6 tools
│   ├── MCP/Service.cls       %AI.MCP.Service at /mcp/kgtickets
│   ├── Ticket/Record.cls     %Persistent table with VECTOR(DOUBLE, 384) column
│   └── Setup/
│       ├── DemoData.cls      Loads 276 tickets from JSON (idempotent)
│       └── MCPSetup.cls      Registers CSP app and tools
├── data/
│   ├── planetcare_demo_tickets.json
│   ├── planetcare_wiki/      Pre-existing KB stubs
│   └── questionnaire_clusters_anon.csv
├── notebooks/
│   ├── planetcare_clustering_demo.ipynb
│   └── planetcare_system_demo.ipynb
├── setup/embedder.py         Local / OpenAI / OpenRouter embedding abstraction
├── requirements.txt
└── .env.example              IRIS connection + embedding + LLM provider config
```

## Requirements

- IRIS AI Hub build 162+ (community edition, free)
- Docker + Docker Compose
- OpenAI API key (for `DraftKBArticle` only — all other tools work without one)
- Claude Desktop, VS Code, or any MCP-compatible client

## Related

- [careconnect-sdoh](../careconnect-sdoh/) — IRIS Interoperability + AI agent example
- [iris-ai-examples](../) — all examples and AI Hub concept index
- [ready2026-knowledge-graph-demo](https://github.com/intersystems-community/ready2026-knowledge-graph-demo) — standalone notebook version with setup scripts

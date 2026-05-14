# KG Ticket Resolver — AI Hub Example

A support ticket knowledge mining agent built on InterSystems IRIS AI Hub.

Ask Claude: *"How complete is ticket PC-00145? Find similar billing tickets and draft a KB article."*

The agent calls 6 MCP tools backed by IRIS:

1. `ScoreTicketCompleteness` — MDS scoring: is this ticket data-rich enough for KB generation?
2. `FindSimilarTickets` — semantic vector search across 276 PlanetCare tickets via iris-vector-graph
3. `GetClusterSummary` — describe the resolution pattern for a ticket category
4. `DraftKBArticle` — synthesize a KB article using a `%AI.Agent` inside IRIS
5. `GetWikiStatus` — show existing wiki articles and documented knowledge gaps
6. `PublishKBArticle` — write an approved article to the wiki + record provenance in Graph_KG

## What it shows

- **`%AI.Agent`** — AI Hub agent running inside IRIS, called via MCP
- **`%AI.ToolSet`** — 6 domain-specific tools exposed via the MCP server
- **iris-vector-graph** — `kg_NodeEmbeddings` for semantic ticket search
- **Graph_KG provenance** — `AUTHORED_KB` and `SOURCED_KB` edges trace every article to its source tickets
- **MDS scoring** — Minimum Data Set completeness check before KB generation
- **PlanetCare wiki** — pre-existing docs with knowledge gaps, augmented by the agent

## Quickstart

### 1. Get the AI Hub image

Download `irishealth-community-2026.2.0AI.162.0-docker.tar.gz` from:
https://evaluation.intersystems.com/Eval/early-access/AIHub

```bash
docker load < irishealth-community-2026.2.0AI.162.0-docker.tar.gz
```

### 2. Start the stack

```bash
export OPENAI_API_KEY=sk-...
cd docker
docker compose up -d
```

Wait ~90 seconds. IRIS initializes, loads 276 demo tickets, and registers 6 MCP tools.

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
        "--iris-port", "1972",
        "--iris-user", "_SYSTEM",
        "--iris-password", "SYS",
        "--iris-endpoint", "/mcp/kgtickets"
      ]
    }
  }
}
```

Restart Claude Desktop. The `kgtickets` server appears with 6 tools.

### 4. Try it

```
"What's the MDS score for ticket PC-00001?"

"Find billing tickets similar to 'invoice amount mismatch'"

"Show me the cluster summary for BILLING and draft a KB article"

"What's the current wiki status? Which categories have knowledge gaps?"

"Draft and publish a KB article for PHARMACY"
```

## Jupyter Notebooks

For data science exploration of the same pipeline:

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
jupyter notebook notebooks/
```

| Notebook | What it shows |
|----------|--------------|
| `planetcare_clustering_demo.ipynb` | MDS gap analysis → HDBSCAN clustering → resolution anchoring → KB article via `%AI.Agent` |
| `planetcare_system_demo.ipynb` | iris-vector-graph API: `kg_KNN_VEC`, `kg_VECTOR_GRAPH_SEARCH`, `kg_GRAPH_WALK` |

The notebooks use the same 276 PlanetCare tickets and the same IRIS instance.

## Demo data

All data is synthetic — no real patient data, no real hospital names.

| File | Description |
|------|-------------|
| `data/planetcare_demo_tickets.json` | 276 synthetic PlanetCare EMR tickets · 7 categories · 42% resolved / 58% open |
| `data/questionnaire_clusters_anon.csv` | 295 anonymized questionnaire tickets with cluster labels |
| `data/planetcare_wiki/` | Pre-existing KB articles with documented knowledge gaps |

## Knowledge Graph Provenance

Every KB article published by the agent is recorded in Graph_KG:

```cypher
MATCH (agent)-[:AUTHORED_KB]->(kb:KBArticle)<-[:SOURCED_KB]-(ticket)
RETURN agent, kb.article_id, kb.category, ticket.ticket_id
LIMIT 20
```

## Architecture

```
Claude Desktop / VS Code
    ↓ MCP (stdio)
iris-mcp-server
    ↓
KGTicketResolver.Tools.ToolSet   ← %AI.ToolSet registered on /mcp/kgtickets
    ├── ScoreTicketCompleteness  ← SQL query on Ticket.Record
    ├── FindSimilarTickets       ← iris-vector-graph kg_NodeEmbeddings
    ├── GetClusterSummary        ← SQL aggregate + resolution extraction
    ├── DraftKBArticle           ← %AI.Agent + %AI.Provider("openai")
    ├── GetWikiStatus            ← file system + SQL
    └── PublishKBArticle         ← file write + Graph_KG rdf_edges
```

## Requirements

- IRIS AI Hub build 162+ (community edition, free)
- Docker + Docker Compose
- OpenAI API key
- Claude Desktop, VS Code, or any MCP-compatible client

## Related

- [iris-vector-graph](https://github.com/intersystems-community/iris-vector-graph) — the graph + vector engine used here
- [careconnect-sdoh](../careconnect-sdoh/) — healthcare SDoH agent example
- [ready2026-knowledge-graph-demo](https://github.com/intersystems-community/ready2026-knowledge-graph-demo) — standalone notebook version with setup scripts

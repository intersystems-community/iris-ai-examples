<!-- markdownlint-disable MD013 MD060 -->

# iris-ai-examples — Agent Context

This repo shows how **iris-agentic-dev + iris-vector-graph + iris-devtester + iris-ai**
fit together. Study these examples to understand the full IRIS AI stack. Every pattern
here has been demo-proven at InterSystems READY 2026.

**Three examples, two tech stacks:**

| Example               | Stack              | AI Hub APIs                                                   | Key IRIS feature                                |
| --------------------- | ------------------ | ------------------------------------------------------------- | ----------------------------------------------- |
| `careconnect-sdoh/`   | ObjectScript + MCP | `%AI.ToolSet`, `%AI.MCP.Service`                              | IRIS Interoperability BS→BP→BO                  |
| `kg-ticket-resolver/` | ObjectScript + MCP | `%AI.ToolSet`, `%AI.MCP.Service`, `%AI.Agent`, `%AI.Provider` | IRIS native vector search + Graph_KG provenance |
| `careconnect-python/` | Python + iris_llm  | `iris_llm.Agent` (@tool decorator)                            | Python-first, no ObjectScript                   |

---

## Ecosystem Map — Which Package Does What

| Package                  | Layer                                                       | Used in                                    | Install                                                                 |
| ------------------------ | ----------------------------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------- |
| `iris-agentic-dev` (iad) | Dev MCP server — compile, execute, query                    | All examples (for development)             | `brew install intersystems-community/iris-agentic-dev/iris-agentic-dev` |
| `iris-devtester`         | Container lifecycle — attach, port resolve, pytest fixtures | All examples (for testing)                 | `pip install iris-devtester`                                            |
| `iris-vector-graph`      | Graph walk, PPR, KNN, embedding indexing on IRIS globals    | `kg-ticket-resolver/`                      | `pip install iris-vector-graph`                                         |
| `iris-vector-rag`        | 6 retrieval strategies, RAGAS eval harness                  | `kg-ticket-resolver/` notebooks            | `pip install iris-vector-rag`                                           |
| AI Hub EAP (`%AI.*`)     | ObjectScript agent + tool SDK                               | `careconnect-sdoh/`, `kg-ticket-resolver/` | Ships with IRIS 2026.2.0AI.162.0+                                       |
| `iris_llm` (Python SDK)  | Python-native agent + tool orchestration                    | `careconnect-python/`                      | Wheel ships inside IRIS image at `/usr/irissys/dev/python/`             |

---

## CareConnect SDoH (`careconnect-sdoh/`)

**What it demonstrates:** An AI agent for Social Determinants of Health screening.
A community health worker tells Claude: _"Assess Maria Gonzalez for SDoH risks and trigger
a follow-up."_ Claude calls 9 MCP tools, scores 6 USDHHS SDoH domains, drafts a care plan,
and fires an IRIS Interoperability workflow.

**Primary teaching goal:** Show that an LLM agent can _observe and control_ an IRIS
Interoperability production — not just query data. The `TriggerFollowUp` tool calls
`Ens.Director` and `CreateBusinessService` to fire a real BS→BP→BO pipeline.

### Key ObjectScript Classes

| Class                              | Role                                                              |
| ---------------------------------- | ----------------------------------------------------------------- |
| `CareConnect.Tools.SDoHToolSet`    | `%AI.ToolSet` — 9 tools, 6-domain keyword scorer, care plan logic |
| `CareConnect.MCP.Service`          | `%AI.MCP.Service` — exposes tools at `/mcp/careconnect`           |
| `CareConnect.Agent.SDoHAssessment` | `%AI.Agent` — optional; tools work via MCP directly               |
| `CareConnect.Production`           | `Ens.Production` — BS → BP → BO wiring                            |
| `CareConnect.Patient`              | `%Persistent` demo patient table (3 seeded patients)              |
| `CareConnect.Setup.DemoData`       | Idempotent seed: 3 demo patients                                  |
| `CareConnect.Setup.MCPSetup`       | Registers CSP app + starts production                             |

### SDoH Domains Scored (6)

Economic Stability · Education Access · Health Care Access · Neighborhood/Built
Environment · Social & Community Context · **Transportation Access** (added after original
5-domain USDHHS framing — transport was buried in Health Care Access before)

### How to Run

```bash
cd careconnect-sdoh/docker
docker compose up -d
# Wait ~90s, then connect MCP client per README
```

Container: `careconnect-iris` (port 1972 superserver, 52773 web)
MCP endpoint: `/mcp/careconnect`

### Eval Suite (no API key needed)

```bash
cd careconnect-sdoh/evals
python run_evals.py
```

Scores: deterministic regression, clinician-truth recall, tool-use trajectory, Interop
audit trail, LLM-as-judge. The 4th golden case (`maria-paraphrase-adversarial`) is
designed to fail L1 — intentional, not a bug.

### iad Tools Relevant While Developing

| Task                           | iad tool                     |
| ------------------------------ | ---------------------------- |
| Compile a modified `.cls` file | `iris_compile`               |
| Run unit tests                 | `iris_test`                  |
| Inspect a global or table      | `iris_query` / `iris_global` |
| Check production message log   | `iris_interop_query`         |
| Search for a class by name     | `iris_search`                |
| Read class docs                | `iris_doc`                   |

---

## KG Ticket Resolver (`kg-ticket-resolver/`)

**What it demonstrates:** A support engineer assistant that mines 276 synthetic EMR
support tickets, scores data completeness via MDS, finds similar tickets with IRIS native
vector search (`VECTOR_COSINE`), and drafts KB articles using a `%AI.Agent` running
_inside IRIS_ — not from Python. Graph_KG records provenance for every published article.

**Primary teaching goal:** `%AI.Agent` + `%AI.Provider` running inside ObjectScript.
The `DraftKBArticle` tool creates a provider, agent, session, and calls `agent.Chat()` —
all in ObjectScript. This is the pattern to study for agents-in-IRIS.

### KG — ObjectScript Classes

| Class                             | Role                                                      |
| --------------------------------- | --------------------------------------------------------- |
| `KGTicketResolver.Tools.ToolSet`  | `%AI.ToolSet` — 6 tools                                   |
| `KGTicketResolver.MCP.Service`    | `%AI.MCP.Service` — exposes tools at `/mcp/kgtickets`     |
| `KGTicketResolver.Ticket.Record`  | `%Persistent` table with `SummaryVec VECTOR(DOUBLE, 384)` |
| `KGTicketResolver.Setup.DemoData` | Loads 276 tickets from JSON (idempotent)                  |
| `KGTicketResolver.Setup.MCPSetup` | Registers CSP app and tools                               |

### Tools

| Tool                      | Key IRIS feature                                                                         |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `ScoreTicketCompleteness` | SQL on `KGTicketResolver_Ticket.Record` — MDS gate                                       |
| `FindSimilarTickets`      | `VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE))` — no external vector DB                |
| `GetClusterSummary`       | SQL aggregates + anchor ticket extraction                                                |
| `DraftKBArticle`          | `%AI.Agent` + `%AI.Provider("openai")` running inside IRIS (**requires OPENAI_API_KEY**) |
| `GetWikiStatus`           | Filesystem check + SQL coverage by category                                              |
| `PublishKBArticle`        | File write + `AUTHORED_KB`/`SOURCED_KB` edges into `Graph_KG.rdf_edges`                  |

### Vector Search SQL Pattern

```sql
SELECT TOP 8 TicketId, Category, Summary,
       VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE)) sim
FROM KGTicketResolver_Ticket.Record
WHERE SummaryVec IS NOT NULL
ORDER BY sim DESC
```

Embeddings optional. Without them, tool falls back to keyword. Seed embeddings via
the notebook cell in `planetcare_clustering_demo.ipynb` (uses local `all-MiniLM-L6-v2`,
no API key).

### Graph_KG Provenance Query

```sql
SELECT s, p, o_id FROM Graph_KG.rdf_edges
WHERE s LIKE 'kb_article:%' OR o_id LIKE 'kb_article:%'
```

Or in Cypher (via iris-vector-graph PPR walk from a seed node).

### KG — How to Run

```bash
export OPENAI_API_KEY=sk-...   # required for DraftKBArticle only
cd kg-ticket-resolver/docker
docker compose up -d
# Wait ~2 min, then connect MCP client per README
```

Container: `kgtickets-iris` (port 1972 superserver, 52773 web)
MCP endpoint: `/mcp/kgtickets`

### KG — iad Tools

| Task                            | iad tool                     |
| ------------------------------- | ---------------------------- |
| Compile or reload ToolSet class | `iris_compile`               |
| Validate SQL with VECTOR_COSINE | `iris_query`                 |
| Inspect Graph_KG edges          | `iris_global` / `iris_query` |
| Check embedding column          | `iris_table_info`            |
| Run setup/seed class            | `iris_execute_method`        |

---

## CareConnect Python (`careconnect-python/`)

**What it demonstrates:** Python-first SDoH agent using `iris_llm.Agent` — no ObjectScript
required. Tools are Python methods with the `@tool` decorator. IRIS data access via
`intersystems-irispython` (`iris.connect()`). Good starting point if you're building
a Python-first application and want the fewest moving parts.

Container: `careconnect-python-iris` (port 1972 superserver)

---

## AI Agent Workflows

### Extend CareConnect with a New Tool

```text
1. Edit careconnect-sdoh/src/CareConnect/Tools/SDoHToolSet.cls
   - Add XData block for the new tool (name, description, parameters)
   - Add the ObjectScript method that implements it

2. Compile:
   iad iris_compile CareConnect.Tools.SDoHToolSet

3. Verify it appears in the catalog:
   iad iris_execute --namespace USER "Do ##class(%AI.ToolMgr).%Discover()"
   (or ask Claude: "list available careconnect tools")

4. Test:
   iad iris_test CareConnect.Tools.SDoHToolSet

5. Eval regression (no API key needed):
   cd careconnect-sdoh/evals && python run_evals.py
```

### Add a New Vector Index (KG Resolver pattern)

```text
1. Define a %Persistent table with a VECTOR column:
   SummaryVec VECTOR(DOUBLE, 384)

2. Compile with: iad iris_compile <YourClass>

3. Validate schema: iad iris_table_info <YourTable>

4. Seed embeddings from Python (iris-devtester attach pattern):
   from iris_devtester import IRISContainer
   c = IRISContainer.attach("kgtickets-iris")
   c.execute_sql("UPDATE ... SET SummaryVec = TO_VECTOR(?, DOUBLE)", [embedding])

5. Validate retrieval: iad iris_query
   SELECT TOP 5 TicketId, VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE)) sim
   FROM YourTable ORDER BY sim DESC

6. Follow iris-vector-graph AGENTS.md for PPR walk patterns on top of the index.
```

### Run Demo Containers (iris-devtester pattern)

```python
from iris_devtester import IRISContainer

# Attach to running container by name
c = IRISContainer.attach("careconnect-iris")

# Run a query
rows = c.execute_sql("SELECT * FROM CareConnect.Patient")

# Execute an ObjectScript method
c.execute("Do ##class(CareConnect.Setup.DemoData).Populate()")
```

Container names come from `docker-compose.yml` in each example's `docker/` directory.

### Fix a Production/Interop Issue

```text
1. Check production status:
   iad iris_production status --namespace USER

2. Check recent message headers:
   iad iris_interop_query --since 1h

3. Restart a stuck component:
   iad iris_execute --namespace USER
   "Do ##class(Ens.Director).StopProduction() Do ##class(Ens.Director).StartProduction()"
```

---

## Where to Look

| Question                                                   | File                                                                                  |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| How are MCP tools defined in ObjectScript?                 | `*/src/*/Tools/*.cls` — `XData ToolDefinitions` block                                 |
| How is the MCP endpoint registered?                        | `*/src/*/MCP/Service.cls` — extends `%AI.MCP.Service`                                 |
| How is the agent defined?                                  | `careconnect-sdoh/src/CareConnect/Agent/SDoHAssessment.cls`                           |
| How does `%AI.Agent` run inside IRIS?                      | `kg-ticket-resolver/src/KGTicketResolver/Tools/ToolSet.cls` — `DraftKBArticle` method |
| How is IRIS Interoperability triggered from an agent tool? | `careconnect-sdoh/src/CareConnect/Tools/SDoHToolSet.cls` — `TriggerFollowUp` method   |
| How are demo patients seeded?                              | `careconnect-sdoh/src/CareConnect/Setup/DemoData.cls`                                 |
| How are 276 tickets loaded from JSON?                      | `kg-ticket-resolver/src/KGTicketResolver/Setup/DemoData.cls`                          |
| How is the IRIS MCP server configured?                     | `*/docker/config.toml` or `*/docker/mcp-config.toml`                                  |
| How does the container start up?                           | `*/docker/iris.script` — compiles classes, seeds data, starts production              |
| Eval suite for CareConnect                                 | `careconnect-sdoh/evals/run_evals.py`                                                 |
| Demo talk track                                            | `careconnect-sdoh/evals/PRESENTATION.md`                                              |
| Python-first agent pattern                                 | `careconnect-python/src/agent.py`                                                     |

---

## Agent Skills to Load

```bash
# Always load for ObjectScript development
skills add iris-agentic-dev

# For KG Ticket Resolver work (vector search, PPR walk)
skills add iris-vector-graph

# For AI Hub %AI.* class patterns
skills add iris-ai-hub

# For RAG pipeline and retrieval strategy selection
skills add iris-vector-rag

# For container lifecycle and pytest fixtures
skills add iris-devtester
```

---

## Container and Port Reference

| Container name            | Port (superserver) | Port (web) | Example               |
| ------------------------- | ------------------ | ---------- | --------------------- |
| `careconnect-iris`        | 1972               | 52773      | `careconnect-sdoh/`   |
| `kgtickets-iris`          | 1972               | 52773      | `kg-ticket-resolver/` |
| `careconnect-python-iris` | 1972               | 52773      | `careconnect-python/` |

Each example is self-contained — containers do not share resources. Run only the
one you're working on.

**Container isolation rule:** These containers are scoped to `iris-ai-examples` only.
Never reference them from other repos, and never start another project's container
(`los-iris`, `opsreview-iris`, `aihub-iris-116`, `careconnect-iris-hub`) from here.
Full registry: `~/ws/productivity-framework/tools/lab_manager/config/iris-container-registry.yaml`.

---

## Requirements

- IRIS AI Hub community build 162+ — download from
  [evaluation.intersystems.com/Eval/early-access/AIHub](https://evaluation.intersystems.com/Eval/early-access/AIHub)
- Docker + Docker Compose
- MCP client: Claude Desktop, VS Code with Claude Code, or Claude CLI
- `OPENAI_API_KEY` — required only for `DraftKBArticle` in `kg-ticket-resolver/` and for
  `careconnect-python/`; all other tools in both examples work without it

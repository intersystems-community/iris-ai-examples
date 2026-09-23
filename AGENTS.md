<!-- markdownlint-disable MD013 MD060 -->

# iris-ai-examples — Agent Context

This repo shows how **iris-agentic-dev + iris-vector-graph + iris-devtester + iris-ai**
fit together. Study these examples to understand the full IRIS AI stack. Every pattern
here has been demo-proven at InterSystems READY 2026.

**Five examples, two tech stacks:**

| Example               | Stack                                         | AI Hub APIs                                                   | Key IRIS feature                                                   |
| --------------------- | --------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
| `careconnect-sdoh/`   | ObjectScript + MCP                            | `%AI.ToolSet`, `%AI.MCP.Service`                              | IRIS Interoperability BS→BP→BO                                     |
| `kg-ticket-resolver/` | ObjectScript + MCP                            | `%AI.ToolSet`, `%AI.MCP.Service`, `%AI.Agent`, `%AI.Provider` | IRIS native vector search + Graph_KG provenance                    |
| `careconnect-python/` | Python + iris_llm                             | `iris_llm.Agent` (@tool decorator)                            | Python-first, no ObjectScript                                      |
| `ai-hub/`             | Both                                          | OTel, ConfigStore, Python bridge, OAuth 2.0, external MCP     | Pattern library — no stack, no seeded data                         |
| `ai-hub-service/`     | Python service + version-neutral ObjectScript | `%AI.MCP.Service` behind a REST contract                      | Agents as a service; meshes a legacy IRIS with an AI Hub companion |

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
a follow-up."_ Claude calls the SDoH tools — 17 in the ToolSet, 10 core and 7 behind
`--profile ivg` — scores 6 USDHHS SDoH domains, drafts a care plan, and fires an IRIS
Interoperability workflow.

**Primary teaching goal:** Show that an LLM agent can _observe and control_ an IRIS
Interoperability production — not just query data. The `TriggerFollowUp` tool calls
`Ens.Director` and `CreateBusinessService` to fire a real BS→BP→BO pipeline.

### Key ObjectScript Classes

| Class                              | Role                                                               |
| ---------------------------------- | ------------------------------------------------------------------ |
| `CareConnect.Tools.SDoHToolSet`    | `%AI.ToolSet` — 17 tools, 6-domain keyword scorer, care plan logic |
| `CareConnect.MCP.Service`          | `%AI.MCP.Service` — exposes tools at `/mcp/careconnect`            |
| `CareConnect.Agent.SDoHAssessment` | `%AI.Agent` — optional; tools work via MCP directly                |
| `CareConnect.Production`           | `Ens.Production` — BS → BP → BO wiring                             |
| `CareConnect.Patient`              | `%Persistent` demo patient table (3 seeded patients)               |
| `CareConnect.Setup.DemoData`       | Idempotent seed: 3 demo patients                                   |
| `CareConnect.Setup.MCPSetup`       | Registers CSP app + starts production                              |

### SDoH Domains Scored (6)

Economic Stability · Education Access · Health Care Access · Neighborhood/Built
Environment · Social & Community Context · **Transportation Access** (added after original
5-domain USDHHS framing — transport was buried in Health Care Access before)

### How to Run

```bash
cd careconnect-sdoh
make up          # docker compose up -d --wait, from the example root
# Wait ~90s, then connect MCP client per README
```

Containers: `careconnect-sdoh-iris-hub` (1973 superserver, 8888 MCP) and `careconnect-sdoh-iris-fhir`
(1974 superserver, 52774 web)
MCP endpoint: `/mcp/careconnect`

Container names carry the `careconnect-sdoh-` prefix because container names are global to the
Docker daemon; the compose file keeps `careconnect-iris-hub` and `careconnect-iris-fhir`
as network aliases, so those remain the correct **hostnames** from inside the stack.
Prefix for `docker exec`, alias for anything that talks over the network.

`careconnect-sdoh/docker-compose.yml` at the example root is the only compose file for the
full stack; `docker-compose.test.yml` adds the IVG profile. An older second build tree
under `careconnect-sdoh/docker/` — a minimal 2-service variant with no FHIR server, no
seeded patients, and no production — was deleted: nothing referenced it, it could not run
alongside the full stack (both published MCP on 8888), and it drifted from the toolset it
was supposed to compile.

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

Container: `kg-ticket-resolver-iris` (port 1972 superserver, 52773 web)
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

## AI Hub Service (`ai-hub-service/`)

**What it demonstrates:** AI Hub delivered as a service rather than an SDK. A REST
contract (`/v1/tools`, `/v1/agents/{a}/runs`, `/v1/runs/{r}/approval`, `/v1/audit`) in
front of a tool catalog, an agent runtime and a governance layer. Proved out on
CareConnect's SDoH agent in three topologies. [DESIGN.md](./ai-hub-service/DESIGN.md) is the argument.

**The one idea:** every tool is bound to a _backend_ — `mcp` (an AI Hub IRIS via
iris-mcp-server), `iris` (any IRIS version via the Native API: SQL or a classmethod), or
`python` (in-process). A deployment mode is just a config file choosing bindings:

| Config (`examples/careconnect/`) | Bindings                                                                                                              |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `offline.yaml`                   | All tools → the eval suite's Python port of SDoHToolSet                                                               |
| `inplace.yaml`                   | All tools → careconnect-sdoh's `/mcp/careconnect`                                                                     |
| `sidecar.yaml`                   | Patient + interop tools → a legacy 2025.1 IRIS over SQL/Native API; scorer + care plan → an AI Hub companion over MCP |

All three extend `base.yaml` (agents, policy, which tools are `write`). A `write` tool
inside a run parks it in `awaiting_approval` until an `approver` decides — enforced by
the runtime, not the prompt.

| Path                          | Role                                                                                                            |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `src/aihub_service/app.py`    | The HTTP contract (FastAPI); `openapi.json` is held equal to it by a test                                       |
| `src/aihub_service/runs.py`   | Run lifecycle: park on approval, resume, reject, audit                                                          |
| `src/aihub_service/backends/` | `mcp`, `iris`, `python`                                                                                         |
| `src/aihub_service/engines/`  | `playbook` (deterministic), `openai`, `anthropic`                                                               |
| `objectscript/AIHub/`         | Version-neutral wrappers: `Client`, `SQL` (`SELECT AIHub.Ask(...)`), `Interop.AgentOperation`, `Legacy.Interop` |
| `deploy/k8s/`                 | kustomize base + `inplace`, `sidecar`, `sidecar-demo` overlays                                                  |

**Rules when editing:** `objectscript/AIHub/*` must stay free of `%AI`, embedded Python
and `%JSON.Adaptor` — it runs on customer IRIS versions that predate AI Hub, and
`tests/test_objectscript.py` enforces it. A new legacy-bound tool needs its classmethod,
table and columns to exist in a shipped class; the same test checks that.

```bash
cd ai-hub-service && python -m pytest        # 116 tests; no Docker, IRIS, or key
PYTHONPATH=src python -m aihub_service --config examples/careconnect/offline.yaml
```

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
   c = IRISContainer.attach("kg-ticket-resolver-iris")
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
c = IRISContainer.attach("careconnect-sdoh-iris-hub")

# Run a query
rows = c.execute_sql("SELECT * FROM CareConnect.Patient")

# Execute an ObjectScript method
c.execute("Do ##class(CareConnect.Setup.DemoData).Populate()")
```

Container names come from each example's compose file — `docker-compose.yml` at the
example root for `careconnect-sdoh/`, `docker/docker-compose.yml` for the other two.
Use the `container_name:` value, not the service key: they differ in `careconnect-sdoh/`.

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

| Question                                                   | File                                                                                           |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| How are MCP tools defined in ObjectScript?                 | `*/src/*/Tools/*.cls` — `XData ToolDefinitions` block                                          |
| How is the MCP endpoint registered?                        | `*/src/*/MCP/Service.cls` — extends `%AI.MCP.Service`                                          |
| How is the agent defined?                                  | `careconnect-sdoh/src/CareConnect/Agent/SDoHAssessment.cls`                                    |
| How does `%AI.Agent` run inside IRIS?                      | `kg-ticket-resolver/src/KGTicketResolver/Tools/ToolSet.cls` — `DraftKBArticle` method          |
| How is IRIS Interoperability triggered from an agent tool? | `careconnect-sdoh/src/CareConnect/Tools/SDoHToolSet.cls` — `TriggerFollowUp` method            |
| How are demo patients seeded?                              | `careconnect-sdoh/src/CareConnect/Setup/DemoData.cls`                                          |
| How are 276 tickets loaded from JSON?                      | `kg-ticket-resolver/src/KGTicketResolver/Setup/DemoData.cls`                                   |
| How is the IRIS MCP server configured?                     | `careconnect-sdoh/services/iris-mcp-sidecar/config.toml`; `*/docker/mcp-config.toml` elsewhere |
| How does the container start up?                           | `careconnect-sdoh/services/iris-ai-hub/iris.script`; `*/docker/iris.script` elsewhere          |
| Eval suite for CareConnect                                 | `careconnect-sdoh/evals/run_evals.py`                                                          |
| Demo talk track                                            | `careconnect-sdoh/evals/PRESENTATION.md`                                                       |
| Python-first agent pattern                                 | `careconnect-python/src/agent.py`                                                              |
| Calling agents from SQL / a production / any IRIS version  | `ai-hub-service/objectscript/AIHub/` — `SQL.cls`, `Interop/AgentOperation.cls`, `Client.cls`   |
| Making legacy SQL or a classmethod an agent tool           | `ai-hub-service/examples/careconnect/sidecar.yaml` — `binding:` blocks                         |
| Human-approval gate for write tools                        | `ai-hub-service/src/aihub_service/runs.py` — `Runner.advance` / `Runner.decide`                |

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

| Container name                  | Port (superserver) | Other published | Example                               |
| ------------------------------- | ------------------ | --------------- | ------------------------------------- |
| `careconnect-sdoh-iris-hub`     | 1973               | 8888 (MCP)      | `careconnect-sdoh/`                   |
| `careconnect-sdoh-iris-fhir`    | 1974               | 52774 (web)     | `careconnect-sdoh/`                   |
| `kg-ticket-resolver-iris`       | 1972               | 52773, 8888     | `kg-ticket-resolver/`                 |
| `careconnect-python-iris`       | 31972              | 31773 (web)     | `careconnect-python/`                 |
| `ai-hub-service-legacy-iris`    | 41972              | 41773 (web)     | `ai-hub-service/` (`sidecar` profile) |
| `ai-hub-service-companion-iris` | 41973              | —               | `ai-hub-service/` (`sidecar` profile) |

`careconnect-sdoh/` also starts `careconnect-sdoh-mcp-sidecar`, `careconnect-sdoh-app`, `careconnect-sdoh-jupyter`,
and — behind profiles — `careconnect-sdoh-ollama` and three `careconnect-sdoh-ivg-*` containers. `ai-hub/`
starts nothing. `ai-hub-service/` starts one service container per profile
(`ai-hub-service-offline`, `-inplace`, `-sidecar`, all on 8080) plus, for `sidecar`,
`ai-hub-service-companion-mcp` in the companion's network namespace.

Each example is self-contained — containers do not share resources. Names cannot collide
any more, but ports still can: `kg-ticket-resolver-iris` and `careconnect-sdoh-iris-hub` both publish MCP
on 8888, so run one example at a time unless you remap.

**Container isolation rule:** The containers above are the only ones this repo owns.
Container names are global to the Docker daemon, so a name that is not in that table may
belong to an unrelated stack on the same machine. Never start, stop, or `docker rm` one
from here — find out what owns it first.

---

## Requirements

- IRIS AI Hub community build 162+ — download from
  [evaluation.intersystems.com/Eval/early-access/AIHub](https://evaluation.intersystems.com/Eval/early-access/AIHub)
- Docker + Docker Compose
- MCP client: Claude Desktop, VS Code with Claude Code, or Claude CLI
- `OPENAI_API_KEY` — required only for `DraftKBArticle` in `kg-ticket-resolver/` and for
  `careconnect-python/`; all other tools in both examples work without it

---

## Known rough edges

The repo grew example by example. These are the seams that have not been cleaned up yet,
recorded so nobody spends an afternoon rediscovering them.

**One build tree in `careconnect-sdoh/`, now that the second is gone.**
`docker-compose.yml` at the example root is canonical — the Makefile, README, `DEMO.md`,
and `docs/eap-setup.md` all drive it. There used to be a self-contained
`careconnect-sdoh/docker/` tree with its own Dockerfile, `entrypoint.sh`, `iris.script`,
two MCP configs, and a 2-service compose file. Nothing outside that directory referenced
it, it could not run alongside the full stack (both published MCP on 8888), and it kept
drifting — its `iris.script` was missing the MCP bit in the web-app `Type`, the defect that
makes an endpoint serve one tool instead of 17. It is deleted. A single-instance variant is
worth having, but as a profile on the canonical compose file rather than a parallel tree.

**The eval mirror is back in parity, and a test that runs keeps it there.**
`careconnect-sdoh/evals/careconnect_evals/tools_local.py` is a hand-written Python mirror of
`SDoHToolSet`, and the whole offline eval suite runs against it. It had drifted three ways at
once — five domains against the ObjectScript's six, transportation folded into Health Care
Access, and URGENT ≥4 / HIGH ≥2 instead of ≥5 / ≥3 — because the only parity check,
`evals/tests/test_parity.py`, skips without a live IRIS, which is exactly the machine where
the mirror gets edited. `evals/tests/test_parity_static.py` now reads `SDoHToolSet.cls` off
disk and asserts the same rule, so it runs everywhere and never skips. Numbers from
`run_evals.py` are quotable about the shipped tool again. See `evals/EVALS.md`, "Keeping the
mirror honest."

**Container names are prefixed, hostnames are not.** `careconnect-sdoh/` publishes
containers as `careconnect-sdoh-*` because container names are global to the Docker daemon
and a bare `careconnect-iris-hub` is generic enough to collide with an unrelated stack on
the same machine. Its compose file keeps
`careconnect-iris-fhir` and `careconnect-iris-hub` as network aliases, which is what
`CareConnect.Tools.SDoHToolSet` falls back to when `FHIR_HOST`/`IVG_HOST` are unset. So
`docker exec` wants the prefix and anything speaking over the network wants the alias.

**Ports can still collide even though names cannot.** `kg-ticket-resolver-iris` and
`careconnect-sdoh-iris-hub` both publish MCP on 8888. Run one example at a time, or remap.

**EAP image tags are written as `<registry>/…`, deliberately.** Four places used to name
the internal ISC registry host outright — `careconnect-sdoh/.env.example`,
`careconnect-sdoh/docs/eap-setup.md`, the header comment of
`careconnect-sdoh/docker-compose.yml`, and `ai-hub/scripts/setup_oauth_test_container.py`.
No external reader can pull from it, so all four now show a `<registry>` placeholder and
say the real prefix comes out of the tarball `docker load` prints. The script no longer
carries a default image at all: it reads `IRIS_IMAGE` and exits with instructions if
that is unset. Keep it that way — a real registry hostname in this repo is public.

**`ai-hub/` is fully checked in now.** `Sample/AI/OAuth/` (six classes plus its own
README), `scripts/`, `tests/unit/`, `tests/integration/test_oauth_rbac.py`, and
`python/rlm/store.py` were all untracked for a while; they are tracked, and
`ai-hub/README.md` documents each one — pattern-table rows, a `scripts/` table, and a test
inventory saying what each suite needs. The OAuth README used to say catalog filtering
needs build 148+; that was measured and retracted (the two-argument `%CanList` and
`%AI.Policy.Discovery` are both present on 139), and the same pass found a real defect it
now records: `RoleDiscovery` declares `Resolve`, but the superclass hook is `%Resolve`, so
it overrides nothing. The OAuth suite runs offline against mocks: 29 passed, no skips.

**SpecKit artifacts do not ship.** `careconnect-sdoh/specs/` used to carry the spec
documents for features 015 and 016 into this public repo. They leak nothing, but they are
internal planning documents rather than example material, so they are no longer tracked
here — they live with the private planning repo that produced them.

**Build numbers look inconsistent but are not, quite.** The root README and `AGENTS.md`
pin the community floor at 2026.2.0AI.162, and the root README says outright that a higher
build named in an example is calling out a later feature, not raising the floor.
`careconnect-sdoh` names 2026.3.0AI.139 in three places — `README.md`, `docs/eap-setup.md`,
`.env.example` — and all three are illustrative: every one is prefixed `e.g.` or followed
by "replace the tag with whatever your tarball produced". So the only real pin in the repo
is 162. Read those 139s as sample output from `docker load`, and do not treat them as a
requirement.

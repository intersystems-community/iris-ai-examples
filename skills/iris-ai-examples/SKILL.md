## <!-- markdownlint-disable MD013 MD041 MD060 -->

name: iris-ai-examples
description: Reference patterns for IRIS AI Hub — CareConnect SDoH (9-tool %AI.ToolSet + Interoperability) and KG Ticket Resolver (%AI.Agent inside IRIS + VECTOR_COSINE + Graph_KG). Load when studying full-stack IRIS AI patterns or starting a new AI Hub application.
author: tdyar
version: 0.1.0
managed_by: iris-ai-examples
source: ~/ws/iris-ai-examples/skills/iris-ai-examples
benchmark_tasks:

- "Find where %AI.Agent is used inside IRIS (not from Python) in these examples"
- "Show the pattern for triggering an IRIS Interoperability workflow from an agent tool"
- "Explain how IRIS native vector search is set up in kg-ticket-resolver"

---

## When to Load This Skill

Load when:

- Studying IRIS AI Hub patterns before writing new code
- Building a new `%AI.ToolSet` or `%AI.MCP.Service`
- Adding Interoperability integration to an AI agent
- Setting up IRIS native vector search (`VECTOR_COSINE`)
- Seeing how `%AI.Agent` + `%AI.Provider` runs inside IRIS

## Quick Reference — CareConnect SDoH

**Repo:** `~/ws/iris-ai-examples/careconnect-sdoh/`

**Entry point:** `src/CareConnect/Tools/SDoHToolSet.cls` — `%AI.ToolSet`, 9 tools, 6-domain
SDoH scorer. Extends `%AI.ToolSet`, each tool is an `XData` block + ObjectScript method.

**MCP endpoint:** `src/CareConnect/MCP/Service.cls` — extends `%AI.MCP.Service`, registered
at `/mcp/careconnect`.

**Interop pattern:** `TriggerFollowUp` method calls `##class(Ens.Director).CreateBusinessService()`
to fire a real BS→BP→BO pipeline from within a tool call.

**Agent class:** `src/CareConnect/Agent/SDoHAssessment.cls` — extends `%AI.Agent`. Has
`XData INSTRUCTIONS` for persona. Tools work via MCP directly without this class.

**Eval suite:** `evals/run_evals.py` — provider-agnostic, no Docker, no API key.

```bash
cd careconnect-sdoh/evals && python run_evals.py
```

## Quick Reference — KG Ticket Resolver

**Repo:** `~/ws/iris-ai-examples/kg-ticket-resolver/`

**Entry point:** `src/KGTicketResolver/Tools/ToolSet.cls` — `%AI.ToolSet`, 6 tools.

**%AI.Agent inside IRIS:** `DraftKBArticle` method in `ToolSet.cls` — creates a
`%AI.Provider("openai")` and `%AI.Agent` in ObjectScript, calls `agent.Chat()`. This is
the canonical pattern for agents running inside IRIS.

**Vector search:** `src/KGTicketResolver/Ticket/Record.cls` — has `SummaryVec VECTOR(DOUBLE, 384)`.
SQL: `VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE))`.

**Graph provenance:** `PublishKBArticle` writes `AUTHORED_KB` / `SOURCED_KB` edges to
`Graph_KG.rdf_edges`.

## Key AI Hub Classes Demonstrated

| Class             | Where                                      | Role                                 |
| ----------------- | ------------------------------------------ | ------------------------------------ |
| `%AI.ToolSet`     | Both examples                              | Define tools as XData + methods      |
| `%AI.MCP.Service` | Both examples                              | Expose ToolSet via MCP endpoint      |
| `%AI.Agent`       | `kg-ticket-resolver/`, `careconnect-sdoh/` | Agent definition + run loop          |
| `%AI.Provider`    | `kg-ticket-resolver/`                      | Configure LLM backend inside IRIS    |
| `iris_llm.Agent`  | `careconnect-python/`                      | Python-first agent (no ObjectScript) |

## Related Skills

- `iris-agentic-dev` — compile, execute, query IRIS via MCP tools (load for all development)
- `iris-ai-hub` — deep reference for `%AI.*` class shapes and EAP caveats
- `iris-vector-graph` — PPR walk, KNN, embedding indexing on top of the vector search pattern
- `iris-vector-rag` — 6 retrieval strategies, RAGAS eval harness

## Container Attach Pattern

```python
from iris_devtester import IRISContainer

# CareConnect SDoH
c = IRISContainer.attach("careconnect-iris")

# KG Ticket Resolver
c = IRISContainer.attach("kgtickets-iris")

rows = c.execute_sql("SELECT * FROM CareConnect.Patient")
c.execute("Do ##class(CareConnect.Setup.DemoData).Populate()")
```

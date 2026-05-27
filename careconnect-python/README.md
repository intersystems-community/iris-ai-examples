# CareConnect SDoH — Python Edition

Python-native SDoH risk assessment agent built with **`iris_llm`** — the InterSystems AI Hub Python SDK.

This example demonstrates the Python-first developer experience on IRIS AI Hub:
- Tools defined as Python class methods with the `@tool` decorator
- Agent orchestration via `iris_llm.Agent` — no ObjectScript required
- IRIS data access via `intersystems-irispython` (`iris.connect()`)
- ObjectScript tools from the companion `careconnect-sdoh` example, bridged via MCP

## Prerequisites

- Docker + Docker Compose
- `irishealth-community:2026.2.0AI.162.0` image loaded locally  
  ([EAP portal download](https://evaluation.intersystems.com/Eval/early-access/AIHub))
- An LLM API key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)

> **Note**: `iris_llm` is part of the IRIS AI Hub EAP. The wheel ships inside the  
> IRIS image at `/usr/irissys/dev/python/` — the Dockerfile copies it from there.  
> No separate download required.

## Quick Start

```bash
cd careconnect-python/docker

cp ../.env.example .env
# Edit .env — set IMAGE tag and API key

docker compose build
docker compose up -d iris
docker compose run agent python agent.py "List all patients"
```

## Architecture

```
agent.py (iris_llm — pure Python)
│
├── SDoHPythonTools (@tool methods)
│   ├── assess_sdoh_risk        — Python keyword scoring over patient text
│   ├── fetch_community_resources — community resource lookup by zip code
│   └── summarize_sdoh_findings — CHW action brief synthesis
│
└── ObjectScript MCP bridge (mcp:remote → IRIS)
    ├── SearchPatients          — FHIR SQL patient roster
    ├── FetchPatientSummary     — clinical summary from IRIS
    └── GetInteropTraces        — Interoperability production traces
```

The `iris_llm` wheel and `intersystems-irispython` are both copied from the IRIS
image at build time via a multi-stage Dockerfile — no bundled wheels in this repo.

## Tool Authoring Pattern

```python
from iris_llm import ToolSet, tool
import iris

class SDoHPythonTools(ToolSet):

    @tool
    def assess_sdoh_risk(self, patient_id: str) -> str:
        """Score a patient on all five USDHHS SDoH domains."""
        conn = iris.connect(hostname="iris", port=1972, ...)
        cur = conn.cursor()
        cur.execute("SELECT Conditions, Notes FROM CareConnect.Patient WHERE PatientId = ?", [patient_id])
        ...
```

This is the same pattern as any LangChain tool — `@tool` generates the JSON schema
that the LLM uses for tool calling.

## Running Interactively

```bash
docker compose run agent
```

```
CareConnect SDoH Agent (iris_llm Python)
CHW> List all patients
CHW> Assess patient P001 for SDoH risk
CHW> Find community resources near zip code 02115 for housing
CHW> Give me a full CHW action brief for Maria Santos
```

## Relation to careconnect-sdoh

| Aspect | careconnect-sdoh | careconnect-python |
|---|---|---|
| Tools | ObjectScript `%AI.ToolSet` | Python `iris_llm.ToolSet` |
| Entry point | Claude Desktop / VS Code MCP | `python agent.py` |
| Data access | FHIR SQL in ObjectScript | `iris.connect()` in Python |
| IRIS required | Yes (MCP server) | Yes (data) + MCP bridge |
| Target audience | ObjectScript devs, IRIS experts | Python/AI developers |

Both examples use the same IRIS container and the same demo patient data.

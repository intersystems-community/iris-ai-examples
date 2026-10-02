# CareConnect SDoH — AI Hub Example

A community health worker types one sentence. The agent scores six SDoH domains, drafts a care plan, and fires an IRIS Interoperability production — all on IRIS, no external services required.

Seventeen tools, rule-based scoring, and no API key needed to run the core workflow.

## Quickstart

### 1. Get the IRIS AI Hub image (EAP)

Full AI Hub features (`%AI.ToolSet`, MCP endpoint, agent orchestration) require
the EAP build. Sign up and download the image tarball:

> **<https://github.com/intersystems-community/ai-hub-eap>**

```bash
docker load < irishealth-ai-hub-2026.x.x.tar
# note the image tag printed — e.g. intersystems/irishealth:2026.3.0AI.139.0
```

See [docs/eap-setup.md](docs/eap-setup.md) for full instructions including what
works without the EAP image.

### 2. Configure environment

```bash
cp .env.example .env
# edit .env — set IRIS_IMAGE and OPENAI_API_KEY (or use --profile ollama)
```

### 3. Start the stack

```bash
docker compose up -d --wait
# With IVG knowledge graph:
# docker compose --profile ivg up -d --wait
```

Wait ~90 seconds. All containers show `healthy` when ready.

### 4. Connect your AI client

The MCP sidecar runs inside the compose stack and exposes the tool endpoint
over HTTP at `http://localhost:8888/mcp/careconnect`.

`iris-mcp-server` is also included in the EAP image for stdio transport.
Create `config.toml` pointing at the hub container's wgproto port (1973):

```toml
[mcp]
transport = "stdio"

[[iris]]
name      = "careconnect"
server    = { host = "localhost", port = 1973, username = "_SYSTEM", password = "SYS" }
pool      = { min = 1, max = 3 }
endpoints = [{ path = "/mcp/careconnect" }]

[logging]
level  = "info"
output = "stderr"
```

> **Port note:** `port = 1973` is the host-mapped IRIS superserver port of the
> `iris-ai-hub` container (1972 inside the container). It is not 8888 — that is
> the HTTP port the in-stack sidecar serves MCP on.

Add to your MCP client config — **Claude CLI** (`~/.claude.json`):

```json
{
  "mcpServers": {
    "careconnect": {
      "command": "/path/to/iris-mcp-server",
      "args": ["--config", "/path/to/config.toml", "run"]
    }
  }
}
```

Same JSON works for VS Code (`.vscode/mcp.json` with `"type": "stdio"`) and
Claude Desktop. Full reference:
[MCP Server Guide](https://github.com/intersystems-community/ai-hub-eap/blob/master/MCP_Server_Guide.md)

### 5. Demo script

[`DEMO.md`](./DEMO.md) is the full 10-minute version: the same prompts with the tool calls
each one triggers and what to say between them. The short form:

**Step through with Claude:**

```text
"List all available patients"

"Fetch the summary for maria-gonzalez-001"

"Search for SDoH protocols matching her conditions"

"Assess her SDoH risk across all six domains"

"Draft a care plan based on those scores"

"Run the action gate for Maria with confidence 0.92 and confirmed consent"

"Start the production and trigger a follow-up for her with priority urgent"

"Show me the interoperability traces"
```

**Or ask Claude to run the full workflow:**

```text
"Do a complete SDoH assessment for James Okafor and trigger a follow-up"
```

## Demo patients

| ID                   | Name                | Conditions                | SDoH risk factors                         |
| -------------------- | ------------------- | ------------------------- | ----------------------------------------- |
| `maria-gonzalez-001` | Maria Gonzalez, 42F | T2 Diabetes, Hypertension | food insecurity, no transport, unemployed |
| `james-okafor-002`   | James Okafor, 67M   | CHF, Depression           | social isolation, housing instability     |
| `sarah-kim-003`      | Sarah Kim, 29F      | Pregnancy 28wk, Anemia    | uninsured, unstable housing               |

## Tools

| Tool                          | What it does                                                                                                                                    |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `SearchPatients`              | List or search the demo patient roster by name, condition, or ID                                                                                |
| `FetchPatientSummary`         | Retrieve clinical conditions, observations, and social context for a patient                                                                    |
| `SearchSDoHProtocols`         | Match USDHHS-aligned screening protocols to the patient's conditions                                                                            |
| `AssessSDoHRisk`              | Score six SDoH domains: Economic Stability, Education Access, Health Care Access, Neighborhood/Built Env, Social Context, Transportation Access |
| `DraftCarePlan`               | Generate prioritized CHW action steps from risk scores                                                                                          |
| `DecideCareAction`            | Ask Liquid AI `d1` Choice, Score, and Noul questions; return `EXECUTE`, `SIMULATE`, `ASK_HUMAN`, or `REJECT` with probabilities                  |
| `StartProduction`             | Start the IRIS Interoperability production (safe if already running)                                                                            |
| `TriggerFollowUp`             | Fire a BS → BP → BO follow-up workflow via `Ens.Director`                                                                                       |
| `GetInteropTraces`            | Show recent message headers: source, target, class, status, timestamp                                                                           |
| `GetProductionStatus`         | Confirm production health and list active components                                                                                            |
| `SearchClinicalNotes`         | Full-text search patient clinical notes                                                                                                         |
| `GetPatientGraphNeighborhood` | Walk the IVG knowledge graph from a patient node (requires `--profile ivg`)                                                                     |
| `FindRelatedEvidence`         | Retrieve evidence nodes related to a clinical concept via IVG (requires `--profile ivg`)                                                        |
| `GetClinicalPathway`          | Return a FHIR + KG combined clinical pathway for a patient question (requires `--profile ivg`)                                                  |
| `CheckProtocolContradictions` | Query IVG for unresolved contradictions between guidelines — blocks the agent if found (requires `--profile ivg`)                               |
| `RecordProtocolDecision`      | Human-approved write: persist a resolved protocol decision into the knowledge graph (requires `--profile ivg`)                                  |
| `GetKnowledgeContext`         | Retrieve all governing decisions for a SDoH concept from IVG (requires `--profile ivg`)                                                         |
| `GroundAnswerWithCitations`   | Verify agent claims against source quotes and add inline citations (requires `--profile ivg`, optional `PARSELTONGUE_GROUNDING=true`)           |

## What it demonstrates

- **`%AI.ToolSet`** — 18 domain-specific tools defined in ObjectScript XData, compiled into IRIS
- **Liquid d1 decision model** — evaluates typed Choice, Score, and Noul questions in one call with zero output tokens; the result is separated from the governed `TriggerFollowUp` write
- **`%AI.MCP.Service`** — exposes the ToolSet on `/mcp/careconnect` via the IRIS web server
- **IRIS Interoperability + AI** — an agent tool triggers a real BS/BP/BO workflow via `Ens.Director`, not just a SQL query
- **Live message tracing** — `GetInteropTraces` reads `Ens.MessageHeader` to show the agent what the production just did
- **MCP sidecar pattern** — `iris-mcp-server` runs alongside IRIS in Docker Compose, sharing the network

## Evaluating the agent

A self-contained, provider-agnostic eval suite lives in [`evals/`](./evals/). It
scores the agent across five layers (deterministic regression, clinician-truth
recall, tool-use trajectory, Interop audit trail outcome, and
LLM-as-judge), and surfaces three real defects the demo script hides — including
a care plan that turns out to be identical for every patient. It runs offline
with no API key:

```bash
cd evals
python run_evals.py
```

See [`evals/EVALS.md`](./evals/EVALS.md) for the lessons and the
measure → fix → re-measure loop.

### Using Liquid d1 for the action gate

The offline service defaults to a deterministic mock so the eval suite needs no
network or API key. To use the real Liquid decision model, create a Liquid API key
(`liquid_...`) and run the service with:

```bash
export LIQUID_API_KEY=liquid_...
export LIQUID_DECISION_MODE=liquid
export LIQUID_DECISION_MODEL=d1:free
python -m aihub_service --config ../ai-hub-service/examples/careconnect/offline.yaml
```

`DecideCareAction` uses [Falconsai/LightDec](https://huggingface.co/Falconsai/LightDec)
by default in local mode: a 0.4B ModernBERT-based, non-autoregressive decision model
with an int8 variant, typed **Choice**, **Score**, and **Noul** questions, calibrated
confidence, and defer behavior. It returns probabilities without text generation.
Set `LIQUID_DECISION_MODE=lightdec` to select it. The previous Liquid d1 integration
remains available with `LIQUID_DECISION_MODE=liquid` and `LIQUID_API_KEY`.
LightDec is used here as a selective workflow gate: its `defer`/low-confidence result
must escalate to a human, and it is not a clinical decision authority.

This follows the same broader direction as Databricks' `ai_decide()` announcement:
decision execution is becoming a first-class data/workflow primitive rather than
only a per-request agent-routing trick. Here, the decision is still separated from
the governed `TriggerFollowUp` write.

## Architecture

```text
Claude Desktop / VS Code / Claude CLI
    │
    ├── MCP over HTTP → localhost:8888/mcp/careconnect      (in-stack sidecar)
    │                     careconnect-sdoh-mcp-sidecar
    │
    └── MCP over stdio → local iris-mcp-server binary       (host-side, step 4)
                          dials localhost:1973
    │
    │  either way, wgproto to the IRIS superserver
    │  (1972 inside the network, published as 1973)
    ▼
CareConnect.MCP.Service  (%AI.MCP.Service at /mcp/careconnect)
    │
    ▼
CareConnect.Tools.SDoHToolSet  (%AI.ToolSet)
    ├── SearchPatients / FetchPatientSummary   ← SQL on CareConnect.Patient
    ├── SearchSDoHProtocols / AssessSDoHRisk   ← rule-based scoring (no LLM)
    ├── DraftCarePlan                          ← rule-based, structured output
    ├── StartProduction / GetProductionStatus  ← Ens.Director
    ├── TriggerFollowUp                        ← Ens.Director → BS → BP → BO
    └── GetInteropTraces                       ← Ens.MessageHeader SQL
```

## Source layout

```text
careconnect-sdoh/
├── Makefile                  up / down / logs / test-* targets
├── docker-compose.yml        Full multi-service stack — the canonical one
├── docker-compose.test.yml   IVG test stack (--profile ivg)
├── .env.example              Copy to .env, set IRIS_IMAGE + API keys
├── docs/
│   └── eap-setup.md          EAP enrollment + image load instructions
├── evals/                    Provider-agnostic eval suite (no API key needed)
├── services/
│   ├── iris-fhir/            FHIR R4 server + demo patient data
│   ├── iris-ai-hub/          IRIS AI Hub (requires EAP image)
│   ├── iris-mcp-sidecar/     MCP stdio bridge (requires EAP image)
│   ├── careconnect/          Python app + Streamlit UI
│   ├── careconnect-ivg/      Knowledge graph bolt API (--profile ivg)
│   └── jupyter/              Notebooks
├── src/CareConnect/
│   ├── Tools/SDoHToolSet.cls     %AI.ToolSet — all 18 tools
│   ├── MCP/Service.cls           %AI.MCP.Service at /mcp/careconnect
│   ├── Agent/SDoHAssessment.cls  %AI.Agent definition
│   ├── Production.cls            Ens.Production wiring
│   ├── agents/                   Python agents (fhir_quality, ops, knowledge_tools)
│   ├── productions/              Python productions (patient_onboarding, sdoh_followup)
│   └── phi_guardian/             PHI scanner + redactor
└── tests/
    ├── unit/                 77 tests, no Docker required
    └── e2e/                  68 tests, need a running stack
        ├── test_stack_smoke.py              7   containers healthy, MCP reachable
        ├── test_stack_contract.py           13  tool contracts
        ├── test_stack_e2e.py                6   full SDoH assessment path
        ├── test_onboarding_contract.py      12  patient-onboarding production
        ├── test_onboarding_e2e.py           4   onboarding end to end
        └── test_ivg_contradiction_gate.py   26  IVG round-trip (--profile ivg)
```

## Notes for demos

- All 18 tools work without an OpenAI API key — risk scoring, care planning, and the action gate are rule-based; IVG tools require the `--profile ivg` stack
- The Interoperability production starts automatically at container startup via `iris.script`
- `TriggerFollowUp` will return an error if the production isn't running — use `StartProduction` first, or just ask Claude to handle it
- `GetInteropTraces` shows message headers from `Ens.MessageHeader` — each `TriggerFollowUp` call adds a row visible here

## Related

- [kg-ticket-resolver](../kg-ticket-resolver/) — `%AI.Agent` + vector search example
- [iris-ai-examples](../) — all examples and AI Hub concept index

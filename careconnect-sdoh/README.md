# CareConnect SDoH — AI Hub Example

A healthcare AI agent for Social Determinants of Health (SDoH) assessment, built on InterSystems IRIS AI Hub.

A community health worker tells Claude: *"Assess Maria Gonzalez for SDoH risks and trigger a follow-up."*

Claude calls 9 MCP tools backed by IRIS, scores all five USDHHS SDoH domains, drafts a prioritized care plan, and fires an IRIS Interoperability workflow — all in one conversation.

## Quickstart

### 1. Get the AI Hub image

Download `irishealth-community-2026.2.0AI.162.0-docker.tar.gz` from:
https://evaluation.intersystems.com/Eval/early-access/AIHub

```bash
docker load < irishealth-community-2026.2.0AI.162.0-docker.tar.gz
```

### 2. Start the stack

```bash
cd docker
docker compose up -d
```

Wait ~90 seconds. IRIS initializes, seeds 3 demo patients, starts the Interoperability production, and registers 9 MCP tools.

### 3. Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "careconnect": {
      "command": "docker",
      "args": [
        "exec", "-i", "careconnect-mcp",
        "/usr/irissys/bin/iris-mcp-server",
        "run",
        "--iris-host", "localhost",
        "--iris-port", "1972",
        "--iris-user", "_SYSTEM",
        "--iris-password", "SYS",
        "--iris-endpoint", "/mcp/careconnect"
    }
  }
}
```

Restart Claude Desktop. The `careconnect` server appears with 9 tools.

### 4. Demo script

**Step through with Claude:**

```
"List all available patients"

"Fetch the summary for maria-gonzalez-001"

"Search for SDoH protocols matching her conditions"

"Assess her SDoH risk across all five domains"

"Draft a care plan based on those scores"

"Start the production and trigger a follow-up for her with priority urgent"

"Show me the interoperability traces"
```

**Or ask Claude to run the full workflow:**
```
"Do a complete SDoH assessment for James Okafor and trigger a follow-up"
```

## Demo patients

| ID | Name | Conditions | SDoH risk factors |
|----|------|------------|-------------------|
| `maria-gonzalez-001` | Maria Gonzalez, 42F | T2 Diabetes, Hypertension | food insecurity, no transport, unemployed |
| `james-okafor-002` | James Okafor, 67M | CHF, Depression | social isolation, housing instability |
| `sarah-kim-003` | Sarah Kim, 29F | Pregnancy 28wk, Anemia | uninsured, unstable housing |

## Tools

| Tool | What it does |
|------|-------------|
| `SearchPatients` | List or search the demo patient roster by name, condition, or ID |
| `FetchPatientSummary` | Retrieve clinical conditions, observations, and social context for a patient |
| `SearchSDoHProtocols` | Match USDHHS-aligned screening protocols to the patient's conditions |
| `AssessSDoHRisk` | Score all 5 SDoH domains: Economic, Education, Health Care, Neighborhood, Social |
| `DraftCarePlan` | Generate prioritized CHW action steps from risk scores |
| `StartProduction` | Start the IRIS Interoperability production (safe if already running) |
| `TriggerFollowUp` | Fire a BS → BP → BO follow-up workflow via `Ens.Director` |
| `GetInteropTraces` | Show recent message headers: source, target, class, status, timestamp |
| `GetProductionStatus` | Confirm production health and list active components |

## What it demonstrates

- **`%AI.ToolSet`** — 9 domain-specific tools defined in ObjectScript XData, compiled into IRIS
- **`%AI.MCP.Service`** — exposes the ToolSet on `/mcp/careconnect` via the IRIS web server
- **IRIS Interoperability + AI** — an agent tool triggers a real BS/BP/BO workflow via `Ens.Director`, not just a SQL query
- **Live message tracing** — `GetInteropTraces` reads `Ens.MessageHeader` to show the agent what the production just did
- **MCP sidecar pattern** — `iris-mcp-server` runs alongside IRIS in Docker Compose, sharing the network

## Architecture

```
Claude Desktop / VS Code
    │
    │  MCP (stdio via docker exec)
    ▼
iris-mcp-server  (kgtickets-mcp container)
    │
    │  HTTP to IRIS web server :52773
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

```
careconnect-sdoh/
├── docker/
│   ├── docker-compose.yml    Two services: iris (full stack) + mcp (sidecar)
│   ├── Dockerfile            Builds IRIS image with classes pre-compiled + data seeded
│   └── iris.script           Compiles all classes, seeds demo data, starts production
└── src/CareConnect/
    ├── Tools/SDoHToolSet.cls     %AI.ToolSet — all 9 tools
    ├── MCP/Service.cls           %AI.MCP.Service at /mcp/careconnect
    ├── Agent/SDoHAssessment.cls  %AI.Agent definition (optional — tools work via MCP directly)
    ├── Production.cls            Ens.Production wiring BS/BP/BO
    ├── Patient.cls               %Persistent demo patient table
    ├── Message/                  FollowUpRequest + FollowUpResponse message classes
    ├── Service/SDoHFollowUpBS.cls   BusinessService
    ├── Process/SDoHFollowUpBP.cls   BusinessProcess
    ├── Operation/SDoHFollowUpBO.cls BusinessOperation
    └── Setup/
        ├── DemoData.cls          Seeds 3 demo patients (idempotent)
        └── MCPSetup.cls          Registers CSP app + starts production
```

## Notes for demos

- All 9 tools work without an OpenAI API key — risk scoring and care planning are rule-based
- The Interoperability production starts automatically at container startup via `iris.script`
- `TriggerFollowUp` will return an error if the production isn't running — use `StartProduction` first, or just ask Claude to handle it
- `GetInteropTraces` shows message headers from `Ens.MessageHeader` — each `TriggerFollowUp` call adds a row visible here

## Related

- [kg-ticket-resolver](../kg-ticket-resolver/) — `%AI.Agent` + vector search example
- [iris-ai-examples](../) — all examples and AI Hub concept index

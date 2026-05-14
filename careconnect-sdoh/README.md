# CareConnect SDoH — AI Hub Example

A healthcare AI agent for Social Determinants of Health (SDoH) assessment, built on InterSystems IRIS AI Hub.

## What it does

A community health worker asks Claude: *"Assess Maria Gonzalez for SDoH risks and draft a care plan."*

Claude calls 9 MCP tools backed by IRIS:
1. `SearchPatients` — finds Maria in the demo patient database
2. `FetchPatientSummary` — retrieves her conditions (T2 Diabetes, Hypertension) and social context
3. `SearchSDoHProtocols` — matches screening protocols to her conditions
4. `AssessSDoHRisk` — scores all 5 USDHHS SDoH domains (Economic, Education, Health Care, Neighborhood, Social)
5. `DraftCarePlan` — generates prioritized CHW action steps
6. `StartProduction` — ensures the Interop production is running
7. `TriggerFollowUp` — fires a BS→BP→BO workflow via IRIS Interoperability
8. `GetInteropTraces` — shows the message flow as text
9. `GetProductionStatus` — confirms production health

## Quickstart

### 1. Get the AI Hub image

Download `irishealth-community-2026.2.0AI.162.0-docker.tar.gz` (ARM64 for Mac) from:
https://evaluation.intersystems.com/Eval/early-access/AIHub

Load it:
```bash
docker load < irishealth-community-2026.2.0AI.162.0-docker.tar.gz
```

### 2. Start the stack

```bash
cd docker
docker compose up -d
```

Wait ~90 seconds for IRIS to initialize. The MCP server starts automatically once IRIS is healthy.

### 3. Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "careconnect": {
      "command": "docker",
      "args": [
        "exec", "-i", "careconnect-iris",
        "/usr/irissys/bin/iris-mcp-server",
        "run",
        "--iris-host", "localhost",
        "--iris-port", "1972",
        "--iris-user", "_SYSTEM",
        "--iris-password", "SYS",
        "--iris-endpoint", "/mcp/careconnect"
      ]
    }
  }
}
```

Restart Claude Desktop. The `careconnect` server will appear with 9 tools.

### 4. Try it

In Claude Desktop:
> *"Search for patients with diabetes and run a full SDoH assessment"*

Or step by step:
> *"Use SearchPatients to list all patients"*
> *"Fetch the summary for maria-gonzalez-001"*
> *"Assess her SDoH risk and draft a care plan"*
> *"Start the production and trigger a follow-up for her"*
> *"Show me the interop traces"*

## Demo patients

| ID | Name | Conditions | SDoH flags |
|---|---|---|---|
| `maria-gonzalez-001` | Maria Gonzalez, 42F | T2 Diabetes, Hypertension | food insecurity, no transport, unemployed |
| `james-okafor-002` | James Okafor, 67M | CHF, Depression | social isolation, housing issues |
| `sarah-kim-003` | Sarah Kim, 29F | Pregnancy 28wk, Anemia | uninsured, unstable housing |

## Architecture

```
Claude Desktop
  └── MCP (iris-mcp-server)
        └── CareConnect.MCP.Service (%AI.MCP.Service)
              └── CareConnect.Tools.SDoHToolSet (%AI.ToolSet)
                    ├── Patient SQL queries (CareConnect.Patient)
                    ├── Ens.Director → CareConnect.Production
                    │     ├── SDoHFollowUpBS (BusinessService)
                    │     ├── SDoHFollowUpBP (BusinessProcess)
                    │     └── SDoHFollowUpBO (BusinessOperation)
                    └── Ens.MessageHeader → interop traces
```

## Source layout

```
src/CareConnect/
  Tools/SDoHToolSet.cls      %AI.ToolSet — all 9 tools
  MCP/Service.cls            %AI.MCP.Service at /mcp/careconnect
  Agent/SDoHAssessment.cls   %AI.Agent with CHW workflow prompt
  Production.cls             Ens.Production (BS/BP/BO wiring)
  Message/FollowUpRequest.cls
  Message/FollowUpResponse.cls
  Service/SDoHFollowUpBS.cls
  Process/SDoHFollowUpBP.cls
  Operation/SDoHFollowUpBO.cls
  Patient.cls                %Persistent demo patient table
  Setup/DemoData.cls         Seeds 3 demo patients (idempotent)
  Setup/MCPSetup.cls         Registers CSP app + starts production
```

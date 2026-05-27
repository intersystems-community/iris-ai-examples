# CareConnect Python Demo Script

## Story

Maria Santos is a 58-year-old patient with Type 2 diabetes and hypertension.
Her CHW, using a Python-native AI agent backed by IRIS AI Hub, assesses her
social risk factors and generates an action plan — all without writing ObjectScript.

## Setup

```bash
cd docker
docker compose build && docker compose up -d iris
# Wait ~90s for IRIS to start
docker compose run agent python agent.py
```

## Step 1 — List patients

```
CHW> List all available patients
```

Expected: roster including P001 Maria Santos, P002 James Chen, etc.

## Step 2 — Assess SDoH risk (Python tool)

```
CHW> Assess patient P001 for social determinants of health risk
```

The `assess_sdoh_risk` Python `@tool` method:
- Connects to IRIS via `iris.connect()`
- Fetches conditions, observations, notes from `CareConnect.Patient`
- Scores all 5 USDHHS domains with keyword analysis
- Returns domain scores + evidence keywords

Expected output:
```
SDoH Risk Assessment for Maria Santos (P001) — Python scoring:
  Economic Stability    : HIGH  [afford, income]
  Education Access      : LOW
  Health Care Access    : HIGH  [transport, uninsur]
  Neighborhood/Built Env: HIGH  [food bank, housing]
  Social Context        : LOW

Overall Priority: URGENT (3/5 domains elevated)
```

## Step 3 — Find community resources (Python tool hitting external-style API)

```
CHW> Find community resources near zip code 02115 for food and housing
```

The `fetch_community_resources` Python tool returns local organizations
by zip prefix — demonstrating how Python tools can call external APIs
(211.org, FHIR servers, etc.) that would be awkward in ObjectScript.

## Step 4 — Bridge to ObjectScript MCP tools

```
CHW> Show me the recent interoperability traces for this patient's follow-up workflow
```

This call routes to the IRIS MCP server (`GetInteropTraces`) via
`agent.add_tool("mcp:remote:...")` — showing both surfaces in one conversation.

## Step 5 — Full action brief

```
CHW> Give me a complete CHW action brief for Maria Santos with community resources
```

The `summarize_sdoh_findings` Python tool synthesizes risk scores + resources
into a structured brief with prioritized next steps.

Expected output:
```
CHW Action Brief: Maria Santos (P001)
Priority: URGENT — same-day outreach required

--- Risk Summary ---
  Economic Stability    : HIGH  [afford, income]
  Health Care Access    : HIGH  [transport]
  Neighborhood/Built Env: HIGH  [food bank]

--- Recommended Actions ---
1. IMMEDIATE: Warm transfer to supervising CHW or social worker
2. Document all HIGH-risk domains in care management system
3. Connect with financial assistance navigator (SNAP, Medicaid, emergency rental)
4. Schedule CHW home visit — assess transportation and insurance barriers
5. Schedule 30-day follow-up call to assess progress

--- Local Resources ---
  Greater Boston Food Bank — 617-427-5200
  Heading Home — 617-864-8140
  MBTA Ride Program — 617-222-5123
```

## Key Demo Talking Points

- **`@tool` decorator** — same pattern as LangChain tools, familiar to Python devs
- **`iris.connect()`** — standard Python DB-API, not ObjectScript
- **Multi-surface agents** — Python tools + ObjectScript MCP tools in one agent
- **Wheels ship in the IRIS image** — `iris_llm` is EAP, no separate install
- **No ObjectScript required** to author tools or run the agent

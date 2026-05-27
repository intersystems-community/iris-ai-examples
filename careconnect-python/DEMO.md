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

Expected: roster with patient IDs, names, demographics, and conditions.

```
Available patients:
  james-okafor-002 | James Okafor | 67M
    Conditions: Congestive Heart Failure, Depression
  maria-gonzalez-001 | Maria Gonzalez | 42F
    Conditions: Type 2 Diabetes Mellitus, Hypertension
  sarah-kim-003 | Sarah Kim | 29F
    Conditions: Prenatal care 28 weeks, Iron deficiency anemia
```

## Step 2 — Assess SDoH risk (Python tool)

```
CHW> Assess patient maria-gonzalez-001 for SDoH risk
```

The `assess_sdoh_risk` Python `@tool` method:
- Connects to IRIS via `iris.connect()`
- Fetches conditions, observations, notes from `CareConnect.Patient`
- Scores all 5 USDHHS domains with keyword analysis
- Returns domain scores + evidence keywords

Expected output:
```
SDoH Risk Assessment for Maria Gonzalez (maria-gonzalez-001) — Python scoring:
  Economic Stability    : MEDIUM  [afford]
  Education Access      : MEDIUM  [english]
  Health Care Access    : MEDIUM  [transport]
  Neighborhood/Built Env: MEDIUM  [food bank]
  Social Context        : MEDIUM  [alone]

Overall Priority: ROUTINE (0/5 domains elevated)
```

## Step 3 — Find community resources (Python tool)

```
CHW> Find community resources near zip code 02115 for food and housing
```

The `fetch_community_resources` Python tool returns local organizations
by zip prefix — demonstrating how Python tools can call external APIs
(211.org, FHIR servers, etc.) that would be awkward in ObjectScript.

```
Community resources near 02115 for food and housing:

  Greater Boston Food Bank (food)
    Phone: 617-427-5200
    Services: Emergency food pantry, SNAP enrollment assistance

  Heading Home (housing)
    Phone: 617-864-8140
    Services: Emergency shelter, rapid rehousing, eviction prevention
```

## Step 4 — Full CHW action brief

```
CHW> Give me a complete CHW action brief for patient maria-gonzalez-001 near zip code 02115
```

The agent calls all three tools in sequence — list, assess, resources, summarize —
and produces a structured CHW action brief with prioritized next steps and local referrals.

## Key Demo Talking Points

- **`@tool` decorator** — same pattern as LangChain tools, familiar to Python devs
- **`iris.connect()`** — standard Python DB-API connecting to IRIS patient data
- **Wheels ship inside the IRIS image** — `iris_llm` is EAP, no separate install needed
- **No ObjectScript required** — tools and agent orchestration are pure Python
- **`mcp:remote` bridging** (roadmap) — iris_llm 0.2+ will support combining Python tools with ObjectScript MCP tools in one agent

# CareConnect Demo Script

A 10-minute walkthrough showing an AI agent coordinating a Social Determinants of Health assessment using IRIS AI Hub MCP tools.

## The scenario

A community health worker at a clinic needs to assess a new patient's social situation and ensure she gets the right follow-up care. Instead of manually filling out forms and checking protocols, she asks Claude.

The agent decides which tools to call and in what order, based on what each one returns. The tools are backed by IRIS AI Hub.

---

## Step 1 — Find the patient

**Prompt:**

```text
Who are the patients in the system?
```

**What happens:** Claude calls `SearchPatients` with no arguments. Returns the full roster.

**Expected output:**

```text
Available patients (use patientId with FetchPatientSummary):
  james-okafor-002 | James Okafor | 67M | Congestive Heart Failure|Depression
  maria-gonzalez-001 | Maria Gonzalez | 42F | Type 2 Diabetes Mellitus|Hypertension
  sarah-kim-003 | Sarah Kim | 29F | Prenatal care 28wk|Iron deficiency anemia
```

**Why it matters:** The agent has a patient database. In a real deployment this would query a FHIR server.

---

## Step 2 — Get the clinical picture

**Prompt:**

```text
Tell me about Maria Gonzalez
```

**What happens:** Claude calls `SearchPatients` with query="maria" to find her ID, then `FetchPatientSummary` with patientId="maria-gonzalez-001".

**Expected output:**

```text
Patient: Maria Gonzalez, 42F
Condition: Type 2 Diabetes Mellitus
Condition: Hypertension
Observation: HbA1c = 8.9
Observation: Blood Pressure = 148/92
Note: Patient reports difficulty affording insulin. Lives alone, no transport.
Recently lost job, relying on food bank. Primary language Spanish, limited English.
```

**Why it matters:** The agent pulled structured clinical data and unstructured social context in one call. The note is the key — it contains the SDoH signal.

---

## Step 3 — Match screening protocols

**Prompt:**

```text
What screening protocols apply to her situation?
```

**What happens:** Claude calls `SearchSDoHProtocols` with the conditions it just learned.

**Expected output:**

```text
Protocol: ADA Diabetes Distress Screening (Problem Areas in Diabetes scale)
Protocol: Food Insecurity Screening - Hunger Vital Sign 2-item tool
Protocol: AADE7 Self-Care Behaviors assessment for diabetes management barriers
Protocol: AHA Hypertension Social Needs Screening Tool
Protocol: Housing Instability Screening - iHELP instrument
Protocol: PRAPARE SDoH Screening Tool
Protocol: Community Health Worker Navigation Referral Protocol
```

The last pair — PRAPARE and CHW Navigation — only appears if the string the agent passes
carries the housing, transport, financial or uninsured wording from Maria's note. Pass the
two condition names alone and you get the first five.

**Why it matters:** The agent matched clinical conditions to evidence-based screening protocols — no LLM hallucination, pure rule-based matching against a curated protocol library.

---

## Step 4 — Score all six SDoH domains

**Prompt:**

```text
Assess her social determinants of health risk
```

**What happens:** Claude calls `AssessSDoHRisk` with Maria's patientId, the clinical summary, and the matched protocols.

**Expected output:**

```text
SDoH Risk Assessment for maria-gonzalez-001:
  Economic Stability:      HIGH
  Education Access:        HIGH
  Health Care Access:      MEDIUM
  Neighborhood/Built Env:  HIGH
  Social Context:          HIGH
  Transportation Access:   HIGH
Overall Priority: URGENT (5/6 domains elevated)
```

Health Care Access lands at MEDIUM because Maria's note never mentions being uninsured or
without a doctor — the keyword scorer only elevates that domain on `uninsur`, `no doctor`,
or `clinic`. Five of six is enough for URGENT; the threshold is 5 for URGENT and 3 for HIGH.

**Why it matters:** Five of six domains elevated on the strength of one free-text note. This
patient needs immediate intervention. Five of the six domains are the USDHHS Healthy People
2030 SDoH framework; Transportation Access is this example's own split out of Health Care
Access.

---

## Step 5 — Draft the care plan

**Prompt:**

```text
Draft a care plan for her
```

**What happens:** Claude calls `DraftCarePlan` with Maria's patientId and the risk scores.

**Expected output:**

```text
Care Plan for maria-gonzalez-001:

1. Connect with financial assistance programs - SNAP, Medicaid, emergency rental assistance
2. Schedule CHW home visit within 5 days - assess transportation barriers
3. Enroll in patient transport program or telehealth if available
4. Report housing issues to housing authority - document mold/safety concerns
5. Refer to community social connection program - senior center, peer support group
6. Schedule 30-day follow-up call to assess progress on care plan goals

Priority: Urgent if 5+ domains HIGH - escalate to supervising CHW
```

`DraftCarePlan` selects steps by matching domain names in the scores string it is handed, so
passing the whole `AssessSDoHRisk` block turns on every branch. Hand it a narrower string and
you get a shorter plan.

**Why it matters:** Every step names an action and, where it has one, a timeframe. The care plan is generated from the risk scores, not from the LLM making things up. A human CHW reviews and acts on it.

---

## Step 6 — Trigger the follow-up workflow

**Prompt:**

```text
Trigger an urgent follow-up for Maria and show me what happened in the system
```

**What happens:** Claude calls `StartProduction` (safe if already running), then `TriggerFollowUp` with priority="urgent", then `GetInteropTraces` to show the message flow.

**Expected output from TriggerFollowUp:**

```text
Follow-up triggered for maria-gonzalez-001 (priority=urgent) jobId=3FA8B2C1-4D69-11F1-A8E0-6A9A469A93AC
```

**Expected output from GetInteropTraces:**

```text
Interoperability Traces (4):
[4] 2026-05-20 14:23:11 | SDoHFollowUpBS -> SDoHFollowUpBP | FollowUpRequest  | Completed
[3] 2026-05-20 14:23:11 | SDoHFollowUpBP -> SDoHFollowUpBO | FollowUpRequest  | Completed
[2] 2026-05-20 14:23:11 | SDoHFollowUpBO -> SDoHFollowUpBP | FollowUpResponse | Completed
[1] 2026-05-20 14:23:11 | SDoHFollowUpBP -> SDoHFollowUpBS | FollowUpResponse | Completed
```

**Why it matters:** The AI agent triggered a real IRIS Interoperability workflow. Business Service → Business Process → Business Operation is the same pattern IRIS Interoperability already runs for healthcare data exchange, now triggered by a conversational AI. The traces prove it ran.

---

## Step 7 — Do it all at once

Once you've seen each step, try this single prompt:

**Prompt:**

```text
Do a complete SDoH assessment for James Okafor — find him, assess his risks,
draft a care plan, trigger an urgent follow-up, and show me the message traces.
```

Claude will call all the tools autonomously in the right order. Watch the tool calls appear in the Claude Desktop sidebar as it works through the workflow.

---

## What to highlight in a demo

**For a technical audience:**

- The tools are ObjectScript classmethods in `CareConnect.Tools.SDoHToolSet` — show the source code
- The MCP service is `%AI.MCP.Service` at `/mcp/careconnect` — registered as a CSP application
- The Interop production is a real `Ens.Production` with BS/BP/BO — not a simulation
- `GetInteropTraces` queries `Ens.MessageHeader` directly — permanent audit trail

**For a business audience:**

- The CHW doesn't know what tools exist — she just asks Claude
- The agent decided the order: search → fetch → protocols → assess → plan → trigger
- Nothing left the IRIS server — PHI stays on-premise
- The follow-up is auditable: who triggered it, when, what priority

**For an AI-skeptical audience:**

- Risk scoring is rule-based, not LLM — no hallucination possible on the scores
- Protocol matching is keyword-based against a curated library
- The LLM's job is only to decide which tools to call and present the results
- Every action is logged in `Ens.MessageHeader`

---

## Troubleshooting

**"No patients found"**
The demo data loads automatically on first boot. If missing: restart the container.

**"Production is not running"**
Ask Claude: _"Start the production"_ — or the first `TriggerFollowUp` call will tell you to.

**Tools don't appear in Claude Desktop**
Restart Claude Desktop after adding the MCP server config. The server appears under Settings → Developer → MCP Servers.

**Port conflict on startup**
The stack publishes 1973 (hub superserver), 8888 (MCP), 1974 and 52774 (FHIR), 8000/8501
(app), and 8889 (Jupyter). Those are literals in `docker-compose.yml`, not variables — so
edit the `ports:` entry of the offending service and update the port in your MCP client
config to match.

**Container name conflict on startup**
Container names in this stack are prefixed `careconnect-sdoh-`, so they should not collide. If one
does, another stack already owns the name — find it with `docker ps -a --filter
name=careconnect-sdoh` before removing anything. Never `docker rm -f` a name you have not
identified; container names are global to the daemon and the one you remove may belong to
someone else's demo.

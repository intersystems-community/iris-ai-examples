# KG Ticket Resolver — Demo Script

A 15-minute walkthrough showing an AI agent mining support ticket patterns to generate a knowledge base, using IRIS AI Hub MCP tools and IRIS native vector search.

## The scenario

A support operations team has 276 PlanetCare EMR tickets — billing errors, pharmacy issues, lab problems. Most tickets are unresolved or resolved but undocumented. The team wants to turn the resolved ones into a searchable KB. Instead of reading tickets manually, they ask Claude.

The agent scores ticket quality, finds patterns, drafts structured KB articles using a `%AI.Agent` running **inside IRIS** (not called from Python), and publishes them with full provenance recorded in a knowledge graph.

---

## Step 1 — Score a ticket for KB readiness

**Prompt:**
```
What's the MDS completeness score for ticket PC-00001?
```

**What happens:** Claude calls `ScoreTicketCompleteness` with ticketId="PC-00001".

**Expected output:**
```
MDS Score for PC-00001: 100/100 | Tier: HIGH | Category: BILLING | Status: Resolved
```

**Now try a lower-scoring ticket:**
```
Score ticket PC-00145
```

**Expected output:**
```
MDS Score for PC-00145: 65/100 | Tier: MEDIUM | Category: PHARMACY | Status: OPEN
```

**Why it matters:** Not all tickets are ready to generate KB content from. The MDS score gates the pipeline — only HIGH-tier tickets produce useful articles. This prevents the agent from drafting KB articles from incomplete data.

---

## Step 2 — Find similar tickets (vector search)

**Prompt:**
```
Find tickets similar to "invoice amount mismatch after system upgrade"
```

**What happens:** Claude calls `FindSimilarTickets`. Uses IRIS native `VECTOR_COSINE` search if embeddings are seeded, keyword fallback otherwise.

**Expected output (with embeddings):**
```
Similar tickets (vector search):
  PC-00001 [BILLING, sim=0.89]: Claim Rejection due to Incorrect CPT Codes
  PC-00018 [BILLING, sim=0.84]: Incorrect Patient Invoice Amount
  PC-00034 [BILLING, sim=0.81]: Invoice Discrepancy Post-System Upgrade
```

**Expected output (without embeddings — keyword fallback):**
```
No similar tickets found (embeddings not seeded). Run setup/embedder.py to enable vector search.
```

**Why it matters:** IRIS stores a `VECTOR(DOUBLE, 384)` column on the ticket table. No external vector database — the same IRIS instance that runs the application stores and searches the embeddings.

---

## Step 3 — Understand a cluster

**Prompt:**
```
Show me the BILLING cluster summary — how many tickets, how many resolved?
```

**What happens:** Claude calls `GetClusterSummary` with category="BILLING".

**Expected output:**
```
Cluster: BILLING | Total: 73 | Resolved: 41 (56%)
Anchor tickets (resolved):
  PC-00001: Claim Rejection due to Incorrect CPT Codes
  PC-00002: Invoice Discrepancy with Insurance
  PC-00003: Delayed Insurance Claim Processing
```

**Follow up:**
```
What about PHARMACY?
```

**Expected output:**
```
Cluster: PHARMACY | Total: 35 | Resolved: 14 (40%)
Anchor tickets (resolved):
  PC-00115: Issue with medication dispensing
  PC-00118: Pharmacy batch processing errors
```

**Why it matters:** The agent now knows which categories have enough resolved tickets to generate KB content from. BILLING (56% resolved) is a good candidate. LABORATORY (fewer resolved) is not ready yet.

---

## Step 4 — Check the existing wiki

**Prompt:**
```
What's the current wiki status? Which categories have coverage gaps?
```

**What happens:** Claude calls `GetWikiStatus`.

**Expected output:**
```
PlanetCare KB Wiki
  billing.md
  laboratory.md
  pharmacy.md

Coverage:
  BILLING        41/73 (56%) — article exists
  LABORATORY     18/52 (35%) — article exists, LOW coverage
  PHARMACY       14/35 (40%) — article exists
  PRINTING        9/28 (32%) — NO ARTICLE
  INTERFACING    12/31 (39%) — NO ARTICLE
  WAITING_LISTS   8/22 (36%) — NO ARTICLE
  QUESTIONNAIRES  7/33 (21%) — NO ARTICLE
```

**Why it matters:** The wiki has 3 articles covering 3 of 7 categories. PRINTING, INTERFACING, WAITING_LISTS, and QUESTIONNAIRES have no KB coverage despite having resolved tickets.

---

## Step 5 — Draft a KB article (requires OPENAI_API_KEY)

**Prompt:**
```
Draft a KB article for the BILLING cluster
```

**What happens:** Claude calls `DraftKBArticle` with category="BILLING". This calls a `%AI.Agent` running **inside IRIS** — not a Python call to OpenAI, but ObjectScript creating an `%AI.Provider`, `%AI.Agent`, and calling `agent.Chat()`.

**Expected output:**
```
KB ARTICLE -- BILLING
---
# Article: Common Billing Issues and Resolutions

## Problem:
Billing inaccuracies and delays can lead to claim rejections or incorrect
patient invoices. This article outlines common billing issues, their root
causes, and actionable steps for resolution and prevention.

## Root Cause:
1. Incorrect CPT coding
2. Discrepancies between services provided and billed amounts
3. Backlogs in the billing department
...

## Resolution Steps:
### 1. Incorrect CPT Code
- Verify the CPT code against billing guidelines
- Resubmit with corrected code
...
---
Use PublishKBArticle() to publish after review.
```

**Without OPENAI_API_KEY:**
```
OPENAI_API_KEY not set. Cannot draft KB article.
```

**Why it matters:** The LLM call (`%AI.Agent`) runs entirely inside the IRIS process. The KB article is synthesized from real resolved tickets — it's grounded in actual ticket data, not hallucinated. The agent reads PC-00001, PC-00002, PC-00003... and synthesizes patterns across them.

---

## Step 6 — Publish to the wiki

**Prompt:**
```
Publish that article to the wiki
```

**What happens:** Claude calls `PublishKBArticle` with the article content and category. Writes to `data/planetcare_wiki/billing.md` and records `AUTHORED_KB` and `SOURCED_KB` edges in `Graph_KG.rdf_edges`.

**Expected output:**
```
Wiki updated: billing.md (BILLING)
Article ID: kb_article_BILLING_20260520_143201
Provenance in Graph_KG.
Sources: 5 tickets
```

**Query the provenance:**
```sql
SELECT s, p, o_id FROM Graph_KG.rdf_edges
WHERE s LIKE 'kb_article:%'
```

**Why it matters:** Every KB article is traceable. You can see exactly which tickets it was derived from, when it was published, and who triggered it.

---

## Step 7 — Full pipeline in one prompt

```
Score PC-00145, find similar pharmacy tickets, check the wiki status,
and draft and publish a KB article for PHARMACY.
```

Claude will chain all the tools autonomously. Watch the tool calls in the Claude Desktop sidebar — it decides the order based on what each tool returns.

---

## What to highlight

**For a technical audience:**
- `DraftKBArticle` creates `%AI.Provider` and `%AI.Agent` in ObjectScript — the LLM runs inside IRIS, not a Python wrapper
- `FindSimilarTickets` uses `VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE))` — native IRIS vector search, same database
- `PublishKBArticle` writes `Graph_KG.rdf_edges` rows — the provenance is a graph relationship, queryable with SQL or Cypher

**For a business audience:**
- The analyst doesn't know which tickets exist — she just asks Claude
- KB articles are grounded in real resolved cases, not LLM improvisation
- The audit trail is permanent: who asked, which tickets were used, when it was published

**For an AI-skeptical audience:**
- `ScoreTicketCompleteness` and `GetClusterSummary` are pure SQL — no LLM involved
- `DraftKBArticle` only runs if HIGH-tier tickets exist — the scoring gate prevents hallucination from sparse data
- Everything is logged in Graph_KG — no black box

---

## Troubleshooting

**`DraftKBArticle` returns "OPENAI_API_KEY not set"**
```bash
export OPENAI_API_KEY=sk-...
cd docker
docker compose up -d
```
All other tools work without an API key.

**`FindSimilarTickets` returns keyword results only**
Embeddings are not seeded by default. To enable vector search:
```bash
cd kg-ticket-resolver
pip install -r requirements.txt
export IRIS_CONTAINER=kgtickets-iris
python3 setup/embedder.py
```
This embeds all 276 tickets using local `all-MiniLM-L6-v2` — no API key needed.

**Port conflict on startup**
```bash
IRIS_PORT=22972 IRIS_WEB_PORT=22773 MCP_PORT=22888 docker compose up -d
```
Update the Claude Desktop config `--iris-port` to match.

**Tools don't appear in Claude Desktop**
Restart Claude Desktop after adding the MCP config. Check Settings → Developer → MCP Servers.

import json
import os
import sys
import time

import iris as _iris
from iris_vector_graph import IRISGraphEngine

host = os.environ.get("IRIS_HOST", "localhost")
port = int(os.environ.get("IRIS_PORT", 1972))
ns   = os.environ.get("IRIS_NAMESPACE", "CARECONNECT")
user = os.environ.get("IRIS_USERNAME", "_SYSTEM")
pwd  = os.environ.get("IRIS_PASSWORD", "SYS")

print(f"Connecting to IRIS {host}:{port} ns={ns}...", flush=True)
conn = None
for attempt in range(30):
    try:
        conn = _iris.connect(f"{host}:{port}/{ns}", user, pwd)
        print(f"Connected (attempt {attempt + 1})", flush=True)
        break
    except Exception as e:
        print(f"  [{attempt+1}/30] waiting: {e}", flush=True)
        time.sleep(5)

if conn is None:
    print("ERROR: could not connect to IRIS", flush=True)
    sys.exit(1)

print("Initializing IVG schema...", flush=True)
g = IRISGraphEngine(conn, embedding_dimension=384)
g.initialize_schema()
print("IVG schema ready.", flush=True)

cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM Graph_KG.nodes")
row = cursor.fetchone()
print(f"Graph nodes: {row[0] if row else 0}", flush=True)
print("CareConnect IVG ready.", flush=True)
# Seeding happens via FastAPI startup event in careconnect_api.py


# ---------------------------------------------------------------------------
# Persistent knowledge layer — seed demo data
# Called from the FastAPI startup event (via HTTP) after uvicorn is up.
# Using HTTP avoids IVG DBAPI parameter translation bugs.
# Idempotent: skipped if SDoHConcept nodes already exist.
# ---------------------------------------------------------------------------

CONCEPTS = [
    {
        "id": "food_insecurity_screening",
        "name": "Food Insecurity Screening",
        "domain": "Economic Stability",
        "aliases": ["food insecurity", "food desert", "hunger screening",
                    "LOINC 88122-7", "LOINC 88123-5"],
    },
    {
        "id": "housing_instability_threshold",
        "name": "Housing Instability Threshold",
        "domain": "Neighborhood/Built Environment",
        "aliases": ["housing instability", "homelessness risk",
                    "housing insecurity", "Z59"],
    },
    {
        "id": "depression_screening_instrument",
        "name": "Depression Screening Instrument",
        "domain": "Social Context",
        "aliases": ["depression screen", "PHQ", "PHQ-2", "PHQ-9",
                    "mental health screening"],
    },
]

DECISIONS = [
    {
        "id": "decision_food_uspstf_2021",
        "concept_id": "food_insecurity_screening",
        "rule": "Screen using 2-question Hunger Vital Sign (HVS). Score >=1 positive answer = at risk. Refer to community food resources.",
        "source": "USPSTF 2021 Social Needs Screening Recommendation",
        "rationale": "Validated in primary care; 97% sensitivity for food insecurity",
        "effective_date": "2021-04-20",
    },
    {
        "id": "decision_food_aha_2022",
        "concept_id": "food_insecurity_screening",
        "rule": "Screen using AHA 3-question protocol. Require >=2 positive answers before referral to avoid over-referral burden on community programs.",
        "source": "AHA Social Determinants of Health Advisory 2022",
        "rationale": "Higher specificity reduces unnecessary referral load; aligns with resource-constrained community partner capacity",
        "effective_date": "2022-11-01",
    },
    {
        "id": "decision_housing_ada_2020",
        "concept_id": "housing_instability_threshold",
        "rule": "Flag housing instability if patient reports inability to pay rent/mortgage in past 12 months OR has moved >=2 times in past year.",
        "source": "ADA Standards of Medical Care 2020 - Social Determinants",
        "rationale": "Captures hidden instability before literal homelessness; enables early intervention",
        "effective_date": "2020-01-01",
    },
    {
        "id": "decision_housing_cms_2023",
        "concept_id": "housing_instability_threshold",
        "rule": "Flag housing instability only if patient is currently homeless or at imminent risk (eviction notice in hand). Prior 12-month history insufficient for billing qualifier.",
        "source": "CMS Z-code Billing Guidelines 2023",
        "rationale": "Billing qualifier requires current status; historical instability is Z59.1 not Z59.0",
        "effective_date": "2023-01-01",
    },
    {
        "id": "decision_depression_phq2_uspstf",
        "concept_id": "depression_screening_instrument",
        "rule": "Administer PHQ-2 as first-line screen. Score >=3 triggers full PHQ-9 follow-up.",
        "source": "USPSTF Depression Screening Recommendation 2023",
        "rationale": "Two-stage approach minimizes burden; PHQ-2 sensitivity 97% for major depression",
        "effective_date": "2023-06-20",
    },
    {
        "id": "decision_depression_phq9_joint_commission",
        "concept_id": "depression_screening_instrument",
        "rule": "Administer full PHQ-9 directly. Two-question screens miss mild-moderate depression in SDoH-burdened populations; PHQ-9 required for Joint Commission HBIPS measure.",
        "source": "Joint Commission HBIPS-7 Measure Specification 2024",
        "rationale": "Accreditation measure requires PHQ-9 score documented; PHQ-2 pre-screen not accepted as evidence",
        "effective_date": "2024-01-01",
    },
]

CONTRADICTIONS = [
    {
        "id": "contradiction_food_threshold",
        "concept_id": "food_insecurity_screening",
        "statement_a": "Screen positive on >=1 HVS answer (USPSTF 2021)",
        "source_a": "USPSTF 2021",
        "statement_b": "Require >=2 positive answers before referral (AHA 2022)",
        "source_b": "AHA 2022",
        "status": "UNRESOLVED",
        "owner": "Clinical Quality Committee",
    },
    {
        "id": "contradiction_housing_threshold",
        "concept_id": "housing_instability_threshold",
        "statement_a": "Flag instability for any housing disruption in past 12 months (ADA 2020)",
        "source_a": "ADA 2020",
        "statement_b": "Flag only current/imminent homelessness for billing qualification (CMS 2023)",
        "source_b": "CMS 2023",
        "status": "UNRESOLVED",
        "owner": "Revenue Integrity + Clinical Quality",
    },
    {
        "id": "contradiction_depression_instrument",
        "concept_id": "depression_screening_instrument",
        "statement_a": "PHQ-2 first-line; PHQ-9 only if PHQ-2 >=3 (USPSTF 2023)",
        "source_a": "USPSTF 2023",
        "statement_b": "PHQ-9 required directly; PHQ-2 pre-screen not accepted (Joint Commission 2024)",
        "source_b": "Joint Commission 2024",
        "status": "UNRESOLVED",
        "owner": "Quality & Accreditation Office",
    },
]


def _cypher_http(query: str, api_key: str = "changeme", base_url: str = "http://localhost:8000") -> dict:
    """POST a Cypher query to the IVG HTTP API. Returns the JSON response dict."""
    import urllib.request
    import urllib.error
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/cypher",
        data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from /api/cypher: {body}\nQuery: {query[:200]}")


def _seed_knowledge_layer(api_key: str = "changeme", base_url: str = "http://localhost:8000") -> None:
    """Seed SDoH knowledge layer via IVG HTTP API. Idempotent."""
    # Check if already fully seeded (need contradictions, not just concepts)
    check = _cypher_http("MATCH (ct:Contradiction) RETURN count(ct) AS n", api_key, base_url)
    rows = check.get("rows", [])
    if rows and rows[0][0] >= 3:
        print(f"  [knowledge-seed] already seeded ({rows[0][0]} contradictions), skipping.", flush=True)
        return

    print("  [knowledge-seed] seeding SDoH knowledge layer...", flush=True)

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

    # Upsert concepts
    for c in CONCEPTS:
        aliases_json = esc(json.dumps(c["aliases"]))
        q = (
            f'MERGE (c:SDoHConcept {{id: "{esc(c["id"])}"}}) '
            f'SET c.name = "{esc(c["name"])}", '
            f'c.domain = "{esc(c["domain"])}", '
            f'c.aliases = "{aliases_json}"'
        )
        _cypher_http(q, api_key, base_url)

    # Upsert decisions (node only first, then relationship)
    for d in DECISIONS:
        print(f"  [knowledge-seed] decision node: {d['id']}", flush=True)
        _cypher_http(
            f'MERGE (d:SDoHDecision {{id: "{esc(d["id"])}"}}) '
            f'SET d.concept = "{esc(d["concept_id"])}", '
            f'd.rule = "{esc(d["rule"])}", '
            f'd.source = "{esc(d["source"])}", '
            f'd.rationale = "{esc(d["rationale"])}", '
            f'd.effective_date = "{esc(d["effective_date"])}"',
            api_key, base_url,
        )
        print(f"  [knowledge-seed] GOVERNS: {d['id']} -> {d['concept_id']}", flush=True)
        _cypher_http(
            f'MATCH (d:SDoHDecision {{id: "{esc(d["id"])}"}}), '
            f'(c:SDoHConcept {{id: "{esc(d["concept_id"])}"}}) '
            f'MERGE (d)-[:GOVERNS]->(c)',
            api_key, base_url,
        )

    # Upsert contradictions (node only first, then relationship)
    for ct in CONTRADICTIONS:
        print(f"  [knowledge-seed] contradiction: {ct['id']}", flush=True)
        _cypher_http(
            f'MERGE (ct:Contradiction {{id: "{esc(ct["id"])}"}}) '
            f'SET ct.concept = "{esc(ct["concept_id"])}", '
            f'ct.statement_a = "{esc(ct["statement_a"])}", '
            f'ct.source_a = "{esc(ct["source_a"])}", '
            f'ct.statement_b = "{esc(ct["statement_b"])}", '
            f'ct.source_b = "{esc(ct["source_b"])}", '
            f'ct.status = "{esc(ct["status"])}", '
            f'ct.owner = "{esc(ct["owner"])}"',
            api_key, base_url,
        )
        print(f"  [knowledge-seed] CONFLICTS_WITH: {ct['id']}", flush=True)
        _cypher_http(
            f'MATCH (ct:Contradiction {{id: "{esc(ct["id"])}"}}), '
            f'(c:SDoHConcept {{id: "{esc(ct["concept_id"])}"}}) '
            f'MERGE (ct)-[:CONFLICTS_WITH]->(c)',
            api_key, base_url,
        )

    print(
        f"  [knowledge-seed] done — "
        f"{len(CONCEPTS)} concepts, {len(DECISIONS)} decisions, "
        f"{len(CONTRADICTIONS)} contradictions.",
        flush=True,
    )

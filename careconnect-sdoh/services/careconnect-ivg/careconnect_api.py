import json as _json
import os
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from iris_vector_graph.cypher_api import app, _get_engine
from iris_vector_graph.fhir_bridge import unified_clinical_pipeline


# ---------------------------------------------------------------------------
# Demo seed data — 3 concepts, 6 decisions, 3 UNRESOLVED contradictions
# ---------------------------------------------------------------------------

_SEED_CONCEPTS = [
    ("food_insecurity_screening", "Food Insecurity Screening", "Economic Stability",
     '["food insecurity","food desert","hunger screening","LOINC 88122-7","LOINC 88123-5"]'),
    ("housing_instability_threshold", "Housing Instability Threshold", "Neighborhood/Built Environment",
     '["housing instability","homelessness risk","housing insecurity","Z59"]'),
    ("depression_screening_instrument", "Depression Screening Instrument", "Social Context",
     '["depression screen","PHQ","PHQ-2","PHQ-9","mental health screening"]'),
]

_SEED_DECISIONS = [
    ("decision_food_uspstf_2021", "food_insecurity_screening",
     "Screen using 2-question Hunger Vital Sign (HVS). Score >=1 positive answer = at risk. Refer to community food resources.",
     "USPSTF 2021 Social Needs Screening Recommendation",
     "Validated in primary care; 97% sensitivity for food insecurity", "2021-04-20"),
    ("decision_food_aha_2022", "food_insecurity_screening",
     "Screen using AHA 3-question protocol. Require >=2 positive answers before referral to avoid over-referral burden.",
     "AHA Social Determinants of Health Advisory 2022",
     "Higher specificity reduces unnecessary referral load", "2022-11-01"),
    ("decision_housing_ada_2020", "housing_instability_threshold",
     "Flag housing instability if patient reports inability to pay rent/mortgage in past 12 months OR has moved >=2 times.",
     "ADA Standards of Medical Care 2020 - Social Determinants",
     "Captures hidden instability before literal homelessness", "2020-01-01"),
    ("decision_housing_cms_2023", "housing_instability_threshold",
     "Flag housing instability only if patient is currently homeless or at imminent risk. Prior 12-month history insufficient.",
     "CMS Z-code Billing Guidelines 2023",
     "Billing qualifier requires current status; historical instability is Z59.1 not Z59.0", "2023-01-01"),
    ("decision_depression_phq2_uspstf", "depression_screening_instrument",
     "Administer PHQ-2 as first-line screen. Score >=3 triggers full PHQ-9 follow-up.",
     "USPSTF Depression Screening Recommendation 2023",
     "Two-stage approach minimizes burden; PHQ-2 sensitivity 97% for major depression", "2023-06-20"),
    ("decision_depression_phq9_joint_commission", "depression_screening_instrument",
     "Administer full PHQ-9 directly. Two-question screens miss mild-moderate depression in SDoH-burdened populations.",
     "Joint Commission HBIPS-7 Measure Specification 2024",
     "Accreditation measure requires PHQ-9 score; PHQ-2 pre-screen not accepted", "2024-01-01"),
]

_SEED_CONTRADICTIONS = [
    ("contradiction_food_threshold", "food_insecurity_screening",
     "Screen positive on >=1 HVS answer (USPSTF 2021)", "USPSTF 2021",
     "Require >=2 positive answers before referral (AHA 2022)", "AHA 2022",
     "UNRESOLVED", "Clinical Quality Committee"),
    ("contradiction_housing_threshold", "housing_instability_threshold",
     "Flag instability for any housing disruption in past 12 months (ADA 2020)", "ADA 2020",
     "Flag only current/imminent homelessness for billing qualification (CMS 2023)", "CMS 2023",
     "UNRESOLVED", "Revenue Integrity + Clinical Quality"),
    ("contradiction_depression_instrument", "depression_screening_instrument",
     "PHQ-2 first-line; PHQ-9 only if PHQ-2 >=3 (USPSTF 2023)", "USPSTF 2023",
     "PHQ-9 required directly; PHQ-2 pre-screen not accepted (Joint Commission 2024)", "Joint Commission 2024",
     "UNRESOLVED", "Quality and Accreditation Office"),
]


def _cypher_post(query: str, api_key: str = "changeme") -> dict:
    payload = _json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        "http://localhost:8000/api/cypher",
        data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}\nQuery: {query[:200]}")


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seed_knowledge_http(api_key: str = "changeme") -> None:
    check = _cypher_post("MATCH (ct:Contradiction) RETURN count(ct) AS n", api_key)
    rows = check.get("rows", [])
    if rows and rows[0][0] >= 3:
        print(f"  [seed] already complete ({rows[0][0]} contradictions)", flush=True)
        return
    print("  [seed] seeding SDoH knowledge layer...", flush=True)
    for cid, name, domain, aliases in _SEED_CONCEPTS:
        _cypher_post(
            f'MERGE (c:SDoHConcept {{id: "{_q(cid)}"}}) '
            f'SET c.name = "{_q(name)}", c.domain = "{_q(domain)}", c.aliases = "{_q(aliases)}"',
            api_key,
        )
    for did, cid, rule, source, rationale, eff_date in _SEED_DECISIONS:
        _cypher_post(
            f'MERGE (d:SDoHDecision {{id: "{_q(did)}"}}) '
            f'SET d.concept = "{_q(cid)}", d.rule = "{_q(rule)}", '
            f'd.source = "{_q(source)}", d.rationale = "{_q(rationale)}", '
            f'd.effective_date = "{_q(eff_date)}"',
            api_key,
        )
        _cypher_post(
            f'MATCH (d:SDoHDecision {{id: "{_q(did)}"}}), '
            f'(c:SDoHConcept {{id: "{_q(cid)}"}}) MERGE (d)-[:GOVERNS]->(c)',
            api_key,
        )
    for ctid, cid, sa, srca, sb, srcb, status, owner in _SEED_CONTRADICTIONS:
        _cypher_post(
            f'MERGE (ct:Contradiction {{id: "{_q(ctid)}"}}) '
            f'SET ct.concept = "{_q(cid)}", ct.statement_a = "{_q(sa)}", '
            f'ct.source_a = "{_q(srca)}", ct.statement_b = "{_q(sb)}", '
            f'ct.source_b = "{_q(srcb)}", ct.status = "{_q(status)}", '
            f'ct.owner = "{_q(owner)}"',
            api_key,
        )
        _cypher_post(
            f'MATCH (ct:Contradiction {{id: "{_q(ctid)}"}}), '
            f'(c:SDoHConcept {{id: "{_q(cid)}"}}) MERGE (ct)-[:CONFLICTS_WITH]->(c)',
            api_key,
        )
    print(
        f"  [seed] done — {len(_SEED_CONCEPTS)} concepts, "
        f"{len(_SEED_DECISIONS)} decisions, {len(_SEED_CONTRADICTIONS)} contradictions.",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Startup: seed demo knowledge layer after uvicorn is ready
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _startup_seed():
    import asyncio
    import threading

    def _seed():
        import time
        time.sleep(3)  # let uvicorn finish starting
        try:
            api_key = os.environ.get("IVG_API_KEY", "changeme")
            _seed_knowledge_http(api_key=api_key)
        except Exception as exc:
            print(f"  [startup-seed] WARNING: {exc}", flush=True)

    # Run in a background thread so startup doesn't block
    threading.Thread(target=_seed, daemon=True).start()


# ---------------------------------------------------------------------------
# Existing: clinical pipeline
# ---------------------------------------------------------------------------

class PipelineRequest(BaseModel):
    patient_id: str
    query: str = ""
    fhir_base_url: str = ""
    top_k: int = 10
    ppr_top_k: int = 20


@app.post("/api/pipeline")
def clinical_pipeline(req: PipelineRequest):
    engine = _get_engine()
    fhir_url = req.fhir_base_url or os.environ.get("FHIR_BASE_URL", "")
    if not fhir_url:
        raise HTTPException(status_code=400, detail="fhir_base_url required or set FHIR_BASE_URL env var")
    try:
        result = unified_clinical_pipeline(
            engine=engine,
            query=req.query,
            fhir_base_url=fhir_url,
            patient_id=req.patient_id,
            top_k=req.top_k,
            ppr_top_k=req.ppr_top_k,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Knowledge layer: contradiction gate + decision write path
# ---------------------------------------------------------------------------

class ContradictionCheckRequest(BaseModel):
    concept: str
    domain: str = ""


class DecisionRequest(BaseModel):
    concept: str
    domain: str
    rule: str
    source: str
    rationale: str
    effective_date: str = ""          # ISO date string, defaults to today
    embedding: Optional[list] = None  # precomputed float list; computed here if omitted


class KnowledgeContextRequest(BaseModel):
    concept: str


@app.post("/api/knowledge/check-contradictions")
def check_contradictions(req: ContradictionCheckRequest):
    """
    Returns any UNRESOLVED Contradiction nodes linked to the given concept.
    The SDoH agent calls this before citing a protocol — if the result
    contains unresolved contradictions, it must block rather than guess.
    """
    if not req.concept:
        raise HTTPException(status_code=400, detail="concept is required")
    api_key = os.environ.get("IVG_API_KEY", "changeme")
    concept_lc = _q(req.concept.lower())
    cypher = (
        f'MATCH (c:SDoHConcept)<-[:CONFLICTS_WITH]-(ct:Contradiction) '
        f'WHERE (toLower(c.id) CONTAINS "{concept_lc}" '
        f'  OR toLower(c.name) CONTAINS "{concept_lc}" '
        f'  OR toLower(c.aliases) CONTAINS "{concept_lc}") '
        f'  AND ct.status = "UNRESOLVED" '
        f'RETURN ct.id AS ct_id, ct.concept AS ct_concept, '
        f'       ct.statement_a AS statement_a, ct.source_a AS source_a, '
        f'       ct.statement_b AS statement_b, ct.source_b AS source_b, '
        f'       ct.status AS ct_status, ct.owner AS ct_owner '
        f'LIMIT 20'
    )
    try:
        result = _cypher_post(cypher, api_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    columns = result.get("columns", [])
    rows = result.get("rows", [])
    contradictions = []
    for r in rows:
        row = dict(zip(columns, r))
        contradictions.append({
            "id": row.get("ct_id"),
            "concept": row.get("ct_concept"),
            "statement_a": row.get("statement_a"),
            "source_a": row.get("source_a"),
            "statement_b": row.get("statement_b"),
            "source_b": row.get("source_b"),
            "status": row.get("ct_status"),
            "owner": row.get("ct_owner"),
        })
    return {
        "concept": req.concept,
        "unresolved_count": len(contradictions),
        "contradictions": contradictions,
        "blocked": len(contradictions) > 0,
    }


@app.post("/api/knowledge/seed")
def seed_knowledge():
    """
    Seed the demo SDoH knowledge layer (3 concepts, 6 decisions, 3 contradictions).
    Idempotent — safe to call multiple times.
    """
    try:
        api_key = os.environ.get("IVG_API_KEY", "changeme")
        _seed_knowledge_http(api_key=api_key)
        return {"status": "ok", "message": "Demo knowledge layer seeded."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/knowledge/record-decision")
def record_decision(req: DecisionRequest):
    """
    Human-approved write path. Merges a SDoHDecision node into the graph
    and links it to the matching SDoHConcept (created if absent).
    If an embedding is not provided it is computed here via sentence-transformers
    so the concept is immediately vector-searchable.
    """
    if not req.concept or not req.rule or not req.source:
        raise HTTPException(status_code=400, detail="concept, rule, and source are required")

    engine = _get_engine()
    eff_date = req.effective_date or date.today().isoformat()

    # Compute embedding if not supplied
    embedding = req.embedding
    if not embedding:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            text = f"{req.concept} {req.domain} {req.rule}"
            embedding = _model.encode(text).tolist()
        except Exception:
            embedding = []

    # Upsert the parent concept node
    concept_cypher = (
        "MERGE (c:SDoHConcept {id: $cid}) "
        "ON CREATE SET c.name = $name, c.domain = $domain, c.aliases = [] "
        "ON MATCH  SET c.domain = $domain "
        "RETURN c.id AS id"
    )
    try:
        engine.execute_cypher(
            concept_cypher,
            parameters={"cid": req.concept.lower().replace(" ", "_"),
                        "name": req.concept,
                        "domain": req.domain},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"concept upsert failed: {e}")

    decision_id = f"decision_{req.concept.lower().replace(' ', '_')}_{eff_date}"

    # Store embedding as a string property (IVG vector columns require DDL;
    # embedding stored as JSON string for retrieval parity — swap to proper
    # vector column once schema supports dynamic label vectors)
    import json
    emb_json = json.dumps(embedding) if embedding else "[]"

    decision_cypher = (
        "MATCH (c:SDoHConcept {id: $cid}) "
        "MERGE (d:SDoHDecision {id: $did}) "
        "ON CREATE SET d.concept = $concept, d.domain = $domain, "
        "              d.rule = $rule, d.source = $source, "
        "              d.rationale = $rationale, d.effective_date = $eff_date, "
        "              d.embedding_json = $emb_json "
        "MERGE (d)-[:GOVERNS]->(c) "
        "RETURN d.id AS id"
    )
    try:
        engine.execute_cypher(
            decision_cypher,
            parameters={
                "cid": req.concept.lower().replace(" ", "_"),
                "did": decision_id,
                "concept": req.concept,
                "domain": req.domain,
                "rule": req.rule,
                "source": req.source,
                "rationale": req.rationale,
                "eff_date": eff_date,
                "emb_json": emb_json,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"decision write failed: {e}")

    return {"status": "ok", "decision_id": decision_id, "embedded": bool(embedding)}


@app.post("/api/knowledge/context")
def get_knowledge_context(req: KnowledgeContextRequest):
    """
    Retrieves the SDoHConcept node + all governing Decisions for a concept.
    Used by the GetKnowledgeContext tool to ground evidence before the agent answers.
    """
    if not req.concept:
        raise HTTPException(status_code=400, detail="concept is required")
    api_key = os.environ.get("IVG_API_KEY", "changeme")
    concept_lc = _q(req.concept.lower())
    cypher = (
        f'MATCH (c:SDoHConcept) '
        f'WHERE toLower(c.id) CONTAINS "{concept_lc}" '
        f'   OR toLower(c.name) CONTAINS "{concept_lc}" '
        f'   OR toLower(c.aliases) CONTAINS "{concept_lc}" '
        f'OPTIONAL MATCH (d:SDoHDecision)-[:GOVERNS]->(c) '
        f'RETURN c.id AS concept_id, c.name AS concept_name, c.domain AS sdoh_domain, '
        f'       c.aliases AS aliases, '
        f'       d.id AS decision_id, d.rule AS rule, d.source AS src, '
        f'       d.rationale AS rationale, d.effective_date AS effective_date '
        f'LIMIT 20'
    )
    try:
        result = _cypher_post(cypher, api_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if not rows:
        return {"concept": req.concept, "found": False, "decisions": []}

    first = dict(zip(columns, rows[0]))
    decisions = [
        {"decision_id": r.get("decision_id"), "rule": r.get("rule"),
         "source": r.get("src"), "rationale": r.get("rationale"),
         "effective_date": r.get("effective_date")}
        for r in [dict(zip(columns, row)) for row in rows]
        if r.get("decision_id")
    ]
    return {
        "concept": first.get("concept_name") or req.concept,
        "concept_id": first.get("concept_id"),
        "domain": first.get("sdoh_domain"),
        "aliases": first.get("aliases") or [],
        "found": True,
        "decisions": decisions,
    }


# ---------------------------------------------------------------------------
# Parseltongue grounding endpoint (optional — set PARSELTONGUE_GROUNDING=true)
# ---------------------------------------------------------------------------

_GROUNDING_ENABLED = os.environ.get("PARSELTONGUE_GROUNDING", "").lower() in ("1", "true", "yes")


class GroundAnswerRequest(BaseModel):
    answer: str                        # the agent's draft answer text
    decisions: list[dict]              # list of {source, rule, rationale, quote?} from GetKnowledgeContext
    concept: str = ""


class GroundAnswerResponse(BaseModel):
    enabled: bool
    verified_claims: list[dict]        # {claim, source, quote, verified, confidence}
    unverified_claims: list[str]       # claims that could not be grounded
    consistency_issues: list[str]      # cross-source divergences detected
    grounded_answer: str               # answer with [SOURCE] inline citations appended
    pltg_source: str                   # the .pltg program that was evaluated (for demo)


@app.post("/api/knowledge/ground-answer", response_model=GroundAnswerResponse)
def ground_answer(req: GroundAnswerRequest):
    """
    Optional Parseltongue grounding layer. Takes the agent's draft answer and
    the source decisions it used, builds a .pltg evidence system, verifies
    each claim against the verbatim source quotes, and returns:
      - which claims are grounded (quote verified in document text)
      - which are unverified / fabricated
      - cross-source consistency issues (divergent values across documents)
      - the answer with inline [SOURCE: ...] citations appended

    Gated by PARSELTONGUE_GROUNDING=true env var. Returns enabled=false otherwise
    so the agent and demo can check before calling.

    Demo note: set PARSELTONGUE_GROUNDING=true in docker-compose to enable.
    Toggle off to show "without grounding" vs "with grounding" contrast.
    """
    if not _GROUNDING_ENABLED:
        return GroundAnswerResponse(
            enabled=False,
            verified_claims=[],
            unverified_claims=[],
            consistency_issues=[],
            grounded_answer=req.answer,
            pltg_source="",
        )

    try:
        from parseltongue import System, load_source
    except ImportError:
        raise HTTPException(status_code=503, detail="parseltongue-dsl not installed. pip install parseltongue-dsl")

    if not req.decisions:
        raise HTTPException(status_code=400, detail="decisions list required for grounding")

    s = System()

    # Register each decision's source document (use rule text as document body)
    for dec in req.decisions:
        source = dec.get("source", "")
        rule = dec.get("rule", "")
        rationale = dec.get("rationale", "")
        if source and rule:
            doc_text = f"{rule}. {rationale}".strip(". ") + "."
            s.register_document(source, doc_text)

    # Build .pltg program: one fact per decision with evidence quotes
    pltg_lines = [f"; Parseltongue grounding for concept: {req.concept or 'unknown'}"]
    for i, dec in enumerate(req.decisions):
        source = dec.get("source", "")
        rule = dec.get("rule", "")
        quote = dec.get("quote") or rule  # fall back to rule text as the quote
        if not source or not rule:
            continue
        fact_name = f"decision-{i}"
        escaped_source = source.replace('"', '\\"')
        escaped_quote = quote.replace('"', '\\"')
        escaped_rule = rule.replace('"', '\\"')
        pltg_lines.append(
            f'(fact {fact_name} "{escaped_rule}"\n'
            f'    :evidence (evidence "{escaped_source}"\n'
            f'        :quotes ("{escaped_quote}")\n'
            f'        :explanation "governing decision"))'
        )
    pltg_source = "\n".join(pltg_lines)

    try:
        load_source(s, pltg_source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parseltongue load error: {e}")

    # Collect verified vs unverified facts
    verified_claims = []
    unverified_claims = []
    for fact in s.list_facts():
        origin = fact.origin
        if origin is None:
            unverified_claims.append(str(fact.wff))
            continue
        is_verified = getattr(origin, "verified", False)
        verif_list = getattr(origin, "verification", []) or []
        confidence = 0.0
        if verif_list:
            scores = [v.get("confidence", {}).get("score", 0.0) for v in verif_list if isinstance(v, dict)]
            confidence = sum(scores) / len(scores) if scores else 0.0
        entry = {
            "claim": str(fact.wff),
            "source": getattr(origin, "document", ""),
            "quote": (verif_list[0].get("quote", "") if verif_list else ""),
            "verified": is_verified,
            "confidence": round(confidence, 3),
        }
        if is_verified:
            verified_claims.append(entry)
        else:
            unverified_claims.append(str(fact.wff))

    # Check consistency (cross-document divergences)
    consistency_issues = []
    try:
        report = s.consistency()
        if hasattr(report, "issues"):
            for issue in report.issues:
                consistency_issues.append(str(issue))
    except Exception:
        pass

    # Build grounded answer: append inline citations for verified claims
    grounded = req.answer
    for vc in verified_claims:
        citation = f" [SOURCE: {vc['source']}]"
        rule_text = vc["claim"].strip('"')
        if rule_text and rule_text[:30] in grounded and citation not in grounded:
            grounded = grounded.replace(rule_text[:30], rule_text[:30] + citation, 1)
    if verified_claims and "[SOURCE:" not in grounded:
        sources = ", ".join(dict.fromkeys(vc["source"] for vc in verified_claims))
        grounded += f"\n\n*Grounded by: {sources}*"

    return GroundAnswerResponse(
        enabled=True,
        verified_claims=verified_claims,
        unverified_claims=unverified_claims,
        consistency_issues=consistency_issues,
        grounded_answer=grounded,
        pltg_source=pltg_source,
    )


# ---------------------------------------------------------------------------
# Obsidian sync endpoints
# ---------------------------------------------------------------------------

class ObsidianImportRequest(BaseModel):
    dry_run: bool = True


@app.post("/api/knowledge/obsidian-export")
def obsidian_export():
    """
    Export all IVG knowledge nodes (SDoHConcept, SDoHDecision, Contradiction)
    to Markdown files under $OBSIDIAN_VAULT_PATH/KnowledgeGraph/.
    Non-destructive: human-editable frontmatter fields are preserved.
    """
    try:
        from obsidian_sync import export_to_obsidian
        result = export_to_obsidian()
    except ImportError:
        raise HTTPException(status_code=503, detail="obsidian_sync module not available in this deployment")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@app.post("/api/knowledge/obsidian-import")
def obsidian_import(req: ObsidianImportRequest = ObsidianImportRequest()):
    """
    Scan Obsidian vault for human edits to Contradiction notes and write
    status transitions / resolutions back to IVG.
    dry_run=true (default) reports changes without committing them.
    """
    try:
        from obsidian_sync import import_from_obsidian
        result = import_from_obsidian(dry_run=req.dry_run)
    except ImportError:
        raise HTTPException(status_code=503, detail="obsidian_sync module not available in this deployment")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result

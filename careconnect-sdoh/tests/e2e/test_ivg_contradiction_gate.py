"""
E2E test: IVG contradiction gate round-trip.

Requires running IVG stack:
    docker compose --profile ivg up -d --wait   # from the example root

Run with:
    SKIP_DOCKER_UP=true pytest tests/e2e/test_ivg_contradiction_gate.py -v
"""
import os
import time
import pytest
import httpx

pytestmark = [pytest.mark.ivg, pytest.mark.e2e, pytest.mark.docker]

IVG_BASE = os.environ.get("IVG_BASE", "http://localhost:19800")
IVG_API_KEY = os.environ.get("IVG_API_KEY", "changeme")
HEADERS = {"X-API-Key": IVG_API_KEY, "Content-Type": "application/json"}

FOOD_CONCEPT = "food insecurity screening"
HOUSING_CONCEPT = "housing instability threshold"


def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{IVG_BASE}{path}", json=body, headers=HEADERS, timeout=15)
    assert r.status_code == 200, f"POST {path} returned {r.status_code}: {r.text}"
    return r.json()


def _cypher(query: str) -> dict:
    return _post("/api/cypher", {"query": query})


@pytest.fixture(scope="module", autouse=True)
def ivg_healthy():
    """Verify IVG bolt service is up before running any test."""
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = httpx.get(f"{IVG_BASE}/health", timeout=5, headers=HEADERS)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    pytest.skip("IVG bolt service not reachable — start with: docker compose --profile ivg up -d")


# ── Graph seeding ─────────────────────────────────────────────────────────────

class TestGraphSeeding:
    def test_sdoh_concepts_seeded(self):
        result = _cypher("MATCH (c:SDoHConcept) RETURN count(c) AS n")
        n = result["rows"][0][0]
        assert n >= 3, f"Expected ≥3 SDoHConcept nodes, got {n}"

    def test_sdoh_decisions_seeded(self):
        result = _cypher("MATCH (d:SDoHDecision) RETURN count(d) AS n")
        n = result["rows"][0][0]
        assert n >= 6, f"Expected ≥6 SDoHDecision nodes, got {n}"

    def test_contradictions_seeded(self):
        result = _cypher("MATCH (ct:Contradiction) RETURN count(ct) AS n")
        n = result["rows"][0][0]
        assert n >= 3, f"Expected ≥3 Contradiction nodes, got {n}"

    def test_food_concept_exists(self):
        result = _cypher('MATCH (c:SDoHConcept {id: "food_insecurity_screening"}) RETURN c.name AS name')
        assert result["rows"], "food_insecurity_screening concept not found"

    def test_governs_relationships_exist(self):
        result = _cypher("MATCH (d:SDoHDecision)-[:GOVERNS]->(c:SDoHConcept) RETURN count(d) AS n")
        n = result["rows"][0][0]
        assert n >= 6

    def test_conflicts_with_relationships_exist(self):
        result = _cypher("MATCH (ct:Contradiction)-[:CONFLICTS_WITH]->(c:SDoHConcept) RETURN count(ct) AS n")
        n = result["rows"][0][0]
        assert n >= 3


# ── Knowledge context retrieval ───────────────────────────────────────────────

class TestKnowledgeContext:
    def test_context_found_for_food_insecurity(self):
        resp = _post("/api/knowledge/context", {"concept": FOOD_CONCEPT})
        assert resp["found"] is True
        assert "food" in resp["concept"].lower()

    def test_context_returns_decisions(self):
        resp = _post("/api/knowledge/context", {"concept": FOOD_CONCEPT})
        assert len(resp["decisions"]) >= 2

    def test_context_decisions_have_required_fields(self):
        resp = _post("/api/knowledge/context", {"concept": FOOD_CONCEPT})
        for d in resp["decisions"]:
            assert "rule" in d, f"Missing 'rule' in decision: {d}"
            assert "source" in d, f"Missing 'source' in decision: {d}"

    def test_context_not_found_for_unknown_concept(self):
        resp = _post("/api/knowledge/context", {"concept": "xyzzy-unknown-concept-42"})
        assert resp["found"] is False

    def test_context_housing_concept_found(self):
        resp = _post("/api/knowledge/context", {"concept": HOUSING_CONCEPT})
        assert resp["found"] is True


# ── Contradiction gate — BLOCKED path ────────────────────────────────────────

class TestContradictionGateBlocked:
    def test_food_insecurity_is_blocked(self):
        resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
        assert resp["blocked"] is True, f"Expected blocked=true, got: {resp}"

    def test_blocked_response_has_contradiction_list(self):
        resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
        assert "contradictions" in resp
        assert len(resp["contradictions"]) >= 1

    def test_blocked_contradiction_has_both_sources(self):
        resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
        ct = resp["contradictions"][0]
        assert "source_a" in ct
        assert "source_b" in ct

    def test_blocked_contradiction_status_is_unresolved(self):
        resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
        ct = resp["contradictions"][0]
        assert ct["status"] == "UNRESOLVED"

    def test_unresolved_count_positive(self):
        resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
        assert resp.get("unresolved_count", 0) >= 1

    def test_housing_contradiction_also_blocked(self):
        resp = _post("/api/knowledge/check-contradictions", {"concept": HOUSING_CONCEPT})
        assert resp["blocked"] is True


# ── Contradiction gate — RESOLVE → PASS cycle ────────────────────────────────

class TestContradictionGateResolveCycle:
    """
    Resolves food_threshold contradiction, verifies gate passes,
    then resets it to UNRESOLVED so other tests remain stable.
    """

    CONTRADICTION_ID = "contradiction_food_threshold"

    def _set_status(self, status: str):
        _cypher(
            f'MATCH (ct:Contradiction) WHERE ct.id = "{self.CONTRADICTION_ID}" '
            f'SET ct.status = "{status}", ct.resolution_date = "2026-08-26", '
            f'ct.governing = "US Preventive Services Task Force 2021"'
        )

    def test_resolve_then_gate_passes(self):
        self._set_status("RESOLVED")
        try:
            resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
            assert resp["blocked"] is False, f"Expected gate to pass after resolution, got: {resp}"
            assert resp.get("unresolved_count", 0) == 0
        finally:
            self._set_status("UNRESOLVED")

    def test_gate_passes_returns_empty_contradictions(self):
        self._set_status("RESOLVED")
        try:
            resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
            assert resp["contradictions"] == [] or all(
                ct["status"] != "UNRESOLVED" for ct in resp.get("contradictions", [])
            )
        finally:
            self._set_status("UNRESOLVED")

    def test_reset_to_unresolved_restores_block(self):
        self._set_status("RESOLVED")
        self._set_status("UNRESOLVED")
        resp = _post("/api/knowledge/check-contradictions", {"concept": FOOD_CONCEPT})
        assert resp["blocked"] is True


# ── Knowledge context after resolution ───────────────────────────────────────

class TestKnowledgeContextAfterResolution:
    CONTRADICTION_ID = "contradiction_food_threshold"

    def _set_status(self, status: str):
        _cypher(
            f'MATCH (ct:Contradiction) WHERE ct.id = "{self.CONTRADICTION_ID}" '
            f'SET ct.status = "{status}"'
        )

    def test_context_still_returns_decisions_after_resolve(self):
        self._set_status("RESOLVED")
        try:
            resp = _post("/api/knowledge/context", {"concept": FOOD_CONCEPT})
            assert resp["found"] is True
            assert len(resp["decisions"]) >= 2
        finally:
            self._set_status("UNRESOLVED")


# ── No-contradiction concept ──────────────────────────────────────────────────

class TestConceptWithNoContradiction:
    def test_depression_screening_has_contradiction(self):
        resp = _post("/api/knowledge/check-contradictions",
                     {"concept": "depression screening instrument"})
        assert resp["blocked"] is True

    def test_unknown_concept_not_blocked(self):
        resp = _post("/api/knowledge/check-contradictions",
                     {"concept": "xyzzy-unknown-concept-xyz"})
        assert resp["blocked"] is False


# ── Cypher API ────────────────────────────────────────────────────────────────

class TestCypherAPI:
    def test_match_all_nodes_returns_results(self):
        result = _cypher("MATCH (n) RETURN count(n) AS total")
        assert result["rows"][0][0] > 0

    def test_variable_length_path_query(self):
        result = _cypher(
            'MATCH (ct:Contradiction)-[:CONFLICTS_WITH]->(c:SDoHConcept)'
            '<-[:GOVERNS]-(d:SDoHDecision) RETURN ct.id, d.id LIMIT 5'
        )
        assert len(result["rows"]) >= 1

    def test_full_contradiction_subgraph(self):
        result = _cypher(
            'MATCH (ct:Contradiction)-[:CONFLICTS_WITH]->(c:SDoHConcept)'
            ' WHERE ct.id = "contradiction_food_threshold"'
            ' RETURN ct.status, c.id'
        )
        assert result["rows"], "No rows returned for contradiction_food_threshold subgraph"
        row = dict(zip(result["columns"], result["rows"][0]))
        assert row["c_id"] == "food_insecurity_screening"

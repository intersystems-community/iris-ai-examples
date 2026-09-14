"""
CareConnect — Persistent Knowledge Layer Tools (Python / iris_llm)

Alternative path to the ObjectScript SDoHToolSet knowledge methods.
Uses iris_llm ToolSet + @tool decorator so these can be attached to any
iris_llm Agent or LangChain agent without going through the MCP sidecar.

Implements the same three knowledge operations:
  - check_protocol_contradictions  → BLOCKED gate before citing guidelines
  - record_protocol_decision        → human-approved write path with embedding
  - get_knowledge_context           → retrieve traceable governing decisions

Bolt API host/key read from env; falls back to local defaults for dev.

Usage:
    from knowledge_tools import KnowledgeTools
    from iris_llm import Agent, Provider

    agent = Agent(provider, model="gpt-4o-mini")
    agent.add_tool(KnowledgeTools())
    agent.system_prompt = SYSTEM_PROMPT   # include contradiction gate instructions
    response = agent.run("What protocol should I use for food insecurity screening?")
"""

import json
import os
from typing import Optional

import httpx
from iris_llm import ToolSet, tool

_IVG_HOST = os.environ.get("IVG_HOST", "careconnect-ivg-bolt")
_IVG_PORT = int(os.environ.get("IVG_PORT", "8000"))
_IVG_API_KEY = os.environ.get("IVG_API_KEY", "changeme")
_IVG_BASE = f"http://{_IVG_HOST}:{_IVG_PORT}"
_UNAVAILABLE = (
    "Knowledge layer unavailable. "
    "Start IVG stack with: docker compose --profile ivg up -d"
)


def _bolt(path: str, payload: dict) -> dict:
    """POST to bolt API; raises RuntimeError on connectivity failure."""
    try:
        resp = httpx.post(
            f"{_IVG_BASE}{path}",
            json=payload,
            headers={"X-API-Key": _IVG_API_KEY},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise RuntimeError(_UNAVAILABLE)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Bolt API error {exc.response.status_code}: {exc.response.text}") from exc


class KnowledgeTools(ToolSet):
    """
    Persistent knowledge layer tools for SDoH protocol management.

    Wraps the IVG bolt API endpoints added in careconnect_api.py.
    Attach to any iris_llm Agent; the agent must include the contradiction
    gate instructions (see SYSTEM_PROMPT_ADDITION below).
    """

    @tool
    def check_protocol_contradictions(self, concept: str, domain: str = "") -> str:
        """
        Check for unresolved guideline contradictions for an SDoH concept before
        citing any protocol. If BLOCKED is returned, the agent MUST NOT choose
        between conflicting guidelines — escalate to clinical lead instead.

        Args:
            concept: SDoH concept name, e.g. 'food insecurity screening',
                     'housing instability threshold', 'depression screening instrument'
            domain:  Optional SDoH domain for filtering, e.g. 'Economic Stability'
        """
        if not concept:
            return "ERROR: concept is required"
        try:
            data = _bolt("/api/knowledge/check-contradictions", {"concept": concept, "domain": domain})
        except RuntimeError as e:
            return str(e)

        if not data.get("blocked"):
            return f"NO_CONTRADICTIONS: Safe to cite protocols for '{concept}'."

        count = data.get("unresolved_count", 0)
        lines = [
            f"BLOCKED: {count} unresolved guideline contradiction(s) found for '{concept}'.",
            "Do NOT choose between them. Escalate to clinical lead.",
            "",
        ]
        for ct in data.get("contradictions", []):
            lines += [
                f"Contradiction: {ct.get('id')}",
                f"  A: {ct.get('statement_a')} [{ct.get('source_a')}]",
                f"  B: {ct.get('statement_b')} [{ct.get('source_b')}]",
                f"  Owner: {ct.get('owner')}",
                "",
            ]
        return "\n".join(lines)

    @tool
    def record_protocol_decision(
        self,
        concept: str,
        domain: str,
        rule: str,
        source: str,
        rationale: str,
        effective_date: str = "",
    ) -> str:
        """
        Record a human-approved SDoH protocol decision into the persistent knowledge
        graph. The agent may PROPOSE values but a human must explicitly confirm before
        this tool is called. Embedding is computed automatically for vector search.

        Args:
            concept:        SDoH concept this decision governs, e.g. 'food insecurity screening'
            domain:         SDoH domain, e.g. 'Economic Stability'
            rule:           The protocol rule text to record
            source:         Authoritative source, e.g. 'USPSTF 2021'
            rationale:      Why this decision was chosen over alternatives
            effective_date: ISO date string (YYYY-MM-DD); defaults to today if omitted
        """
        if not concept or not domain or not rule or not source:
            return "ERROR: concept, domain, rule, and source are required"
        payload = {
            "concept": concept,
            "domain": domain,
            "rule": rule,
            "source": source,
            "rationale": rationale,
        }
        if effective_date:
            payload["effective_date"] = effective_date
        try:
            data = _bolt("/api/knowledge/record-decision", payload)
        except RuntimeError as e:
            return str(e)

        embedded = "yes" if data.get("embedded") else "no (sentence-transformers unavailable)"
        return (
            f"Decision recorded: {data.get('decision_id')}\n"
            f"Concept: {concept} | Source: {source}\n"
            f"Vector-searchable: {embedded}"
        )

    @tool
    def ground_answer_with_citations(
        self,
        answer: str,
        decisions: str,
        concept: str = "",
    ) -> str:
        """
        Optional Parseltongue grounding layer. Verifies each claim in the draft
        answer against verbatim quotes from the source documents, detects
        cross-source divergences, and returns the answer with inline [SOURCE: ...]
        citations. Only runs when PARSELTONGUE_GROUNDING=true on the bolt service.

        Call AFTER get_knowledge_context and AFTER contradiction gate clears.
        Pass the draft answer and the decisions JSON string from get_knowledge_context.
        If grounding is disabled, returns the original answer unchanged.

        Args:
            answer:    Draft answer text to ground and cite
            decisions: JSON string of decisions list from get_knowledge_context
            concept:   SDoH concept being answered (for context)
        """
        if not answer:
            return "ERROR: answer is required"
        try:
            dec_list = json.loads(decisions) if isinstance(decisions, str) else decisions
        except (json.JSONDecodeError, TypeError):
            return "ERROR: decisions must be a JSON array of decision objects"

        try:
            data = _bolt("/api/knowledge/ground-answer", {
                "answer": answer,
                "decisions": dec_list,
                "concept": concept,
            })
        except RuntimeError as e:
            return str(e)

        if not data.get("enabled"):
            return f"Grounding disabled. Answer: {answer}"

        lines = ["=== Parseltongue Grounding Report ===", ""]
        verified = data.get("verified_claims", [])
        unverified = data.get("unverified_claims", [])
        issues = data.get("consistency_issues", [])

        lines.append(f"Verified claims: {len(verified)}")
        for vc in verified:
            lines.append(f"  ✓ [{vc.get('source')}] \"{vc.get('quote', '')}\" (confidence: {vc.get('confidence', 0):.2f})")

        if unverified:
            lines.append(f"\nUnverified claims: {len(unverified)}")
            for u in unverified:
                lines.append(f"  ✗ [UNVERIFIED] {u}")

        if issues:
            lines.append(f"\nConsistency issues: {len(issues)}")
            for iss in issues:
                lines.append(f"  ⚠ {iss}")

        lines += ["", "Grounded answer:", data.get("grounded_answer", answer)]
        return "\n".join(lines)

    @tool
    def get_knowledge_context(self, concept: str) -> str:
        """
        Retrieve governing protocol decisions for an SDoH concept from the persistent
        knowledge graph. Use this to ground recommendations with traceable, source-linked
        evidence before drafting any care plan section.

        Args:
            concept: SDoH concept name to look up, e.g. 'food insecurity screening'
        """
        if not concept:
            return "ERROR: concept is required"
        try:
            data = _bolt("/api/knowledge/context", {"concept": concept})
        except RuntimeError as e:
            return str(e)

        if not data.get("found"):
            return f"No knowledge context found for '{concept}'. The knowledge graph may not be seeded yet."

        aliases = data.get("aliases") or []
        lines = [
            f"Knowledge context for '{data.get('concept')}' (domain: {data.get('domain')}):",
        ]
        if aliases:
            lines.append(f"  Aliases: {', '.join(aliases)}")
        lines.append("")

        decisions = data.get("decisions") or []
        if not decisions:
            lines.append("No governing decisions recorded yet for this concept.")
        else:
            lines.append("Governing decisions:")
            for d in decisions:
                lines += [
                    f"  [{d.get('effective_date')}] {d.get('source')}",
                    f"    Rule: {d.get('rule')}",
                    f"    Rationale: {d.get('rationale')}",
                    "",
                ]
        return "\n".join(lines)


# System prompt addition — paste into any agent that uses KnowledgeTools
SYSTEM_PROMPT_ADDITION = """
## Contradiction gate — MANDATORY before citing any protocol

Before citing a screening threshold, referral rule, or clinical guideline:

1. Call check_protocol_contradictions with the concept name
2. If the result starts with BLOCKED:
   - Do NOT choose between the conflicting guidelines
   - Do NOT prefer the more recent document
   - Respond: "I cannot make a protocol recommendation for [concept] —
     conflicting guidelines exist. See details below. Escalate to clinical lead."
   - Include the contradiction details from the tool result
3. If the result starts with NO_CONTRADICTIONS, proceed normally

Use get_knowledge_context before drafting any care plan section.
Every recommendation must trace to a source returned by that tool.

## Optional: quote-level citation verification (Parseltongue)

If PARSELTONGUE_GROUNDING is enabled on the service, call
ground_answer_with_citations(answer, decisions_json, concept) after drafting
your answer. This verifies each claim against verbatim quotes from the source
documents and adds inline [SOURCE: ...] citations. If grounding is disabled,
the tool returns the original answer unchanged — calling it is always safe.
"""


if __name__ == "__main__":
    # Smoke test — prints tool catalog without needing a live IVG instance
    kt = KnowledgeTools()
    catalog = kt.get_catalog()
    print(f"KnowledgeTools — {len(catalog)} tools registered:")
    for t in catalog:
        print(f"  {t['name']}: {t.get('description', '')[:80]}")

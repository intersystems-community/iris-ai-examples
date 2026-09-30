"""Liquid AI d1 decision-model integration for CareConnect.

The adapter speaks Liquid's Decision API directly rather than asking a generative
LLM to emit JSON. d1 evaluates typed Choice, Score, and Noul questions and returns
probabilities with zero output tokens.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

import httpx


DEFAULT_BASE_URL = "https://api.liquid.ai"
DEFAULT_MODEL = "d1:free"
DECISION_PATH = "/decisions/v1/systemone"


class LiquidDecisionError(RuntimeError):
    """Raised when Liquid d1 cannot produce a valid decision."""


@dataclass
class LiquidD1Client:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 30.0
    transport: httpx.BaseTransport | None = None

    def decide(self, *, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise LiquidDecisionError("LIQUID_API_KEY is not configured")
        payload = {"model": self.model, "state": state, "questions": questions}
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as http:
                response = http.post(
                    f"{self.base_url.rstrip('/')}{DECISION_PATH}",
                    json=payload,
                )
        except (httpx.HTTPError, TypeError) as exc:
            raise LiquidDecisionError(f"Liquid d1 request failed: {exc}") from exc
        if response.status_code >= 400:
            raise LiquidDecisionError(
                f"Liquid d1 returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise LiquidDecisionError("Liquid d1 returned invalid JSON") from exc
        if not isinstance(body.get("answers"), dict):
            raise LiquidDecisionError("Liquid d1 response has no answers object")
        return body


def _choice(answer: dict[str, Any]) -> tuple[str, float, dict[str, float]]:
    choice = answer.get("choice")
    probabilities = answer.get("probabilities") or {}
    confidence = answer.get("confidence")
    if not isinstance(choice, str) or not isinstance(probabilities, dict):
        raise LiquidDecisionError("Liquid d1 action answer is missing choice/probabilities")
    try:
        conf = float(confidence if confidence is not None else probabilities.get(choice, 0.0))
        probs = {str(k): float(v) for k, v in probabilities.items()}
    except (TypeError, ValueError) as exc:
        raise LiquidDecisionError("Liquid d1 returned non-numeric probabilities") from exc
    return choice, conf, probs


def _score(answer: dict[str, Any]) -> tuple[float, dict[str, float]]:
    try:
        score = float(answer["score"])
        probabilities = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise LiquidDecisionError("Liquid d1 urgency answer is missing score/probabilities") from exc
    return score, probabilities


def _noul(answer: dict[str, Any]) -> float:
    try:
        return float(answer["noul"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LiquidDecisionError("Liquid d1 consent answer is missing noul probability") from exc


def render_d1_decision(patient_id: str, result: dict[str, Any]) -> str:
    """Turn the typed d1 result into the stable text consumed by the playbook."""
    answers = result.get("answers", {})
    action, confidence, probabilities = _choice(answers["action"])
    urgency, urgency_probabilities = _score(answers["urgency"])
    consent_probability = _noul(answers["has_consent"])
    action = action.upper()

    # d1 supplies the decision; these are explicit application safety rails for
    # the downstream side effect, not a replacement for d1's classification.
    if consent_probability < 0.80 and action == "EXECUTE":
        decision = "ASK_HUMAN"
        reason = "d1 consent probability is below the 0.80 safety threshold"
    elif confidence < 0.60 and action in {"EXECUTE", "SIMULATE"}:
        decision = "ASK_HUMAN"
        reason = "d1 action confidence is below the 0.60 safety threshold"
    else:
        decision = action if action in {"EXECUTE", "SIMULATE", "ASK_HUMAN", "REJECT"} else "ASK_HUMAN"
        reason = f"Liquid d1 selected {decision}"

    lines = [
        f"Action Gate for {patient_id} (Liquid d1)",
        f"Decision: {decision}",
        f"d1 action confidence: {confidence:.3f}",
        f"d1 urgency score: {urgency:.3f}",
        f"d1 consent probability: {consent_probability:.3f}",
        f"Action probabilities: {json.dumps(probabilities, sort_keys=True)}",
        f"Urgency probabilities: {json.dumps(urgency_probabilities, sort_keys=True)}",
        f"Reason: {reason}",
    ]
    return "\n".join(lines)


def decide_with_d1(
    patient_id: str,
    risk_assessment: str,
    proposed_action: str = "trigger_follow_up",
    consent: str = "no",
    *,
    client: LiquidD1Client | None = None,
    api_key: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
) -> str:
    """Call d1 for one CareConnect action decision.

    The full state is structured JSON so the model sees the risk assessment,
    requested action, and consent signal as separate fields.
    """
    if not patient_id:
        return "ERROR: patientId is required"
    if proposed_action != "trigger_follow_up":
        return f"Decision: REJECT\nReason: unsupported action '{proposed_action}'"
    client = client or LiquidD1Client(
        api_key=api_key if api_key is not None else os.getenv("LIQUID_API_KEY", ""),
        base_url=base_url,
        model=model,
    )
    questions = {
        "action": {
            "type": "choice",
            "instructions": "What should happen next for this proposed care coordination action?",
            "criteria": {
                "EXECUTE": "Proceed with the proposed trigger_follow_up action when it is safe and appropriate.",
                "SIMULATE": "Prepare or simulate the action without causing a side effect.",
                "ASK_HUMAN": "Escalate to a human because the case is uncertain, sensitive, or needs review.",
                "REJECT": "Do not perform the proposed action.",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this care coordination action?",
            "criteria": {
                "routine": "Can wait for normal workflow timing.",
                "high": "Should be handled promptly.",
                "urgent": "Requires immediate attention.",
            },
        },
        "has_consent": {
            "type": "noul",
            "instructions": "Is patient consent sufficiently confirmed for this proposed action?",
        },
    }
    result = client.decide(
        state={
            "patient_id": patient_id,
            "risk_assessment": risk_assessment,
            "proposed_action": proposed_action,
            "patient_consent": consent,
        },
        questions=questions,
    )
    return render_d1_decision(patient_id, result)


def mock_transport(response: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    """Small helper for tests and examples that need a deterministic d1 response."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response, request=request)

    return handler

"""Regression tests for the Liquid d1 care-action decision model."""

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careconnect_evals.liquid_decision import LiquidD1Client, decide_with_d1, mock_transport  # noqa: E402
from careconnect_evals.tools_local import LocalToolClient  # noqa: E402


URGENT = "SDoH Risk Assessment for maria-gonzalez-001:\nOverall Priority: URGENT (5/6 domains elevated)"
HIGH = "SDoH Risk Assessment for sarah-kim-003:\nOverall Priority: HIGH (3/6 domains elevated)"


def test_urgent_consented_high_confidence_can_execute():
    out = LocalToolClient().DecideCareAction(
        "maria-gonzalez-001", URGENT, confidence="0.92", consent="yes"
    )
    assert "Decision: EXECUTE" in out
    assert "Priority: URGENT" in out


def test_missing_consent_stops_before_a_side_effect():
    out = LocalToolClient().DecideCareAction(
        "maria-gonzalez-001", URGENT, confidence="0.99", consent="no"
    )
    assert "Decision: ASK_HUMAN" in out
    assert "consent is not confirmed" in out


def test_low_confidence_stops_before_a_side_effect():
    out = LocalToolClient().DecideCareAction(
        "maria-gonzalez-001", URGENT, confidence="0.74", consent="yes"
    )
    assert "Decision: ASK_HUMAN" in out
    assert "0.75 decision threshold" in out


def test_high_priority_is_simulated_not_executed():
    out = LocalToolClient().DecideCareAction(
        "sarah-kim-003", HIGH, confidence="0.92", consent="yes"
    )
    assert "Decision: SIMULATE" in out


def test_unsupported_action_is_rejected():
    out = LocalToolClient().DecideCareAction(
        "maria-gonzalez-001", URGENT, proposedAction="send_sms", consent="yes"
    )
    assert out == "Decision: REJECT\nReason: unsupported action 'send_sms'"


def test_liquid_d1_choice_score_and_noul_response_drives_execute():
    response = {
        "model": "d1:free",
        "answers": {
            "action": {
                "type": "choice",
                "choice": "EXECUTE",
                "confidence": 0.94,
                "probabilities": {"EXECUTE": 0.94, "SIMULATE": 0.03, "ASK_HUMAN": 0.02, "REJECT": 0.01},
            },
            "urgency": {
                "type": "score",
                "score": 2.8,
                "probabilities": {"routine": 0.02, "high": 0.08, "urgent": 0.90},
            },
            "has_consent": {"type": "noul", "noul": 0.98},
        },
        "usage": {"output_tokens": 0},
    }
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=response, request=request)

    client = LiquidD1Client("liquid_test", transport=httpx.MockTransport(handler))
    out = decide_with_d1("maria-gonzalez-001", URGENT, consent="yes", client=client)
    assert "(Liquid d1)" in out
    assert "Decision: EXECUTE" in out
    assert "d1 action confidence: 0.940" in out
    assert "d1 urgency score: 2.800" in out
    assert seen["path"] == "/decisions/v1/systemone"
    assert seen["authorization"] == "Bearer liquid_test"
    assert seen["body"]["model"] == "d1:free"
    assert seen["body"]["state"]["patient_id"] == "maria-gonzalez-001"
    assert {q["type"] for q in seen["body"]["questions"].values()} == {"choice", "score", "noul"}


def test_liquid_d1_consent_safety_rail_can_escalate_execute():
    response = {
        "answers": {
            "action": {"type": "choice", "choice": "EXECUTE", "confidence": 0.95, "probabilities": {"EXECUTE": 0.95}},
            "urgency": {"type": "score", "score": 2.5, "probabilities": {"urgent": 1.0}},
            "has_consent": {"type": "noul", "noul": 0.40},
        }
    }
    client = LiquidD1Client("liquid_test", transport=httpx.MockTransport(mock_transport(response)))
    out = decide_with_d1("maria-gonzalez-001", URGENT, consent="yes", client=client)
    assert "Decision: ASK_HUMAN" in out
    assert "consent probability" in out

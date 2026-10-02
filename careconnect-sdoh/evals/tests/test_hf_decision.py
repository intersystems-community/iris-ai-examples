"""Regression tests for the local Hugging Face LightDec adapter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careconnect_evals.hf_decision import decide_with_lightdec  # noqa: E402


class FakeLightDec:
    def __init__(self, response):
        self.response = response
        self.state = None
        self.questions = None

    def decide(self, *, state, questions):
        self.state = state
        self.questions = questions
        return self.response


def _response(action="EXECUTE", confidence=0.94, consent=0.98, defer=False):
    return {
        "answers": {
            "action": {
                "type": "choice",
                "choice": action,
                "confidence": confidence,
                "probs": {action: confidence, "ASK_HUMAN": 1 - confidence},
                "defer": defer,
            },
            "urgency": {
                "type": "score",
                "expected_level": 2.8,
                "probs": {"0": 0.02, "1": 0.08, "2": 0.90},
            },
            "has_consent": {"type": "noul", "p_true": consent},
        }
    }


def test_lightdec_preserves_choice_score_noul_and_state():
    client = FakeLightDec(_response())
    out = decide_with_lightdec("maria-gonzalez-001", "Overall Priority: URGENT", consent="yes", client=client)
    assert "(Hugging Face LightDec)" in out
    assert "Decision: EXECUTE" in out
    assert "LightDec action confidence: 0.940" in out
    assert "LightDec urgency expected level: 2.800" in out
    assert "LightDec consent probability: 0.980" in out
    assert client.state["patient_id"] == "maria-gonzalez-001"
    assert {question["type"] for question in client.questions.values()} == {"choice", "score", "noul"}
    assert isinstance(client.questions["urgency"]["criteria"], list)


def test_lightdec_defer_becomes_human_review():
    out = decide_with_lightdec("maria-gonzalez-001", "Overall Priority: URGENT", consent="yes", client=FakeLightDec(_response(defer=True)))
    assert "Decision: ASK_HUMAN" in out
    assert "deferred" in out


def test_lightdec_does_not_infer_missing_consent_into_a_write():
    out = decide_with_lightdec("maria-gonzalez-001", "risk", consent="no", client=FakeLightDec(_response()))
    assert "Decision: ASK_HUMAN" in out
    assert "consent is not explicitly confirmed" in out


def test_lightdec_rejects_unsupported_side_effect_before_inference():
    client = FakeLightDec(_response())
    out = decide_with_lightdec("maria-gonzalez-001", "risk", proposed_action="send_sms", client=client)
    assert out == "Decision: REJECT\nReason: unsupported action 'send_sms'"
    assert client.state is None

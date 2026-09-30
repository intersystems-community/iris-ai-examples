"""Regression tests for the bounded care-action decision model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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

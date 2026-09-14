"""Sanity tests for the eval harness itself — "who evals the evals?"

These run offline against the mock provider and pin the *known* findings of the
golden set, so a refactor of the scorers can't silently change what the suite
reports. Run with: pytest  (or: python -m pytest)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careconnect_evals import run_suite  # noqa: E402


def _report():
    return run_suite("mock")


def test_adversarial_case_breaks_rule_regression():
    """The paraphrased-summary case must flip URGENT->ROUTINE and fail L1."""
    rep = _report()
    adv = next(r for r in rep["results"] if r["adversarial"])
    assert adv["layers"]["L1_rule_regression"]["passed"] is False
    assert adv["layers"]["L1_rule_regression"]["priority_got"] == "ROUTINE"


def test_non_adversarial_rule_regression_passes():
    rep = _report()
    for r in rep["results"]:
        if not r["adversarial"]:
            assert r["layers"]["L1_rule_regression"]["passed"], r["id"]


def test_clinician_recall_shows_rule_blind_spot():
    """The shipped rule under-calls real needs: recall < 1, precision == 1.

    0.714 is 10 of the 14 domains a clinician marked elevated. It was 0.75 (9/12)
    while the mirror scored five domains and the sixth was invisible to the
    scorer — the number moved because the measurement got wider, not because the
    rule got worse."""
    s = _report()["summary"]
    assert s["human_truth_micro_recall"] == 0.714
    assert s["human_truth_micro_precision"] == 1.0


def test_care_plans_are_not_actually_personalized():
    """L5 must catch that every patient gets the identical plan body."""
    d = _report()["summary"]["care_plan_differentiation"]
    assert d["passed"] is False
    assert d["all_identical"] is True


def test_trajectory_and_outcome_pass_for_all():
    rep = _report()
    for r in rep["results"]:
        assert r["layers"]["L2_trajectory"]["passed"], r["id"]
        assert r["layers"]["L3_outcome"]["passed"], r["id"]


def test_clinical_notes_search_is_pinned_to_a_golden_string():
    """SearchClinicalNotes is the only shipped tool whose ObjectScript talks to
    the FHIR server, so `tests/test_parity.py` cannot compare it byte for byte
    against a live IRIS. Pin the offline port's output instead: the shape here is
    what the ObjectScript prints per DocumentReference entry."""
    from careconnect_evals.tools_local import LocalToolClient

    client = LocalToolClient()

    assert client.SearchClinicalNotes("") == "ERROR: patientId is required"
    assert (
        client.SearchClinicalNotes("nobody-000")
        == "No clinical notes found for patient nobody-000"
    )
    assert client.SearchClinicalNotes("maria-gonzalez-001") == (
        "Clinical notes for maria-gonzalez-001:\n"
        "  [current] 2026-02-14 - Patient reports difficulty affording insulin. "
        "Lives alone, no transport. Recently lost job, relying on food bank. "
        "Primary language Spanish, limited English.\n"
    )
    # The query narrows on the note text, the way `description:contains=` does.
    assert "food bank" in client.SearchClinicalNotes("maria-gonzalez-001", "food bank")
    assert (
        client.SearchClinicalNotes("maria-gonzalez-001", "eviction")
        == "No clinical notes found for patient maria-gonzalez-001"
    )


def test_improvements_close_the_gaps():
    """The proposed fixes must lift clinician recall to 1.0 and differentiate
    plans by risk profile — this is the 'improve' half of the loop, pinned."""
    from careconnect_evals import scorers
    from careconnect_evals.improved import assess_improved, draft_care_plan_improved
    from careconnect_evals.tools_local import LocalToolClient
    import json

    client = LocalToolClient()
    cases = json.load(open(Path(__file__).resolve().parent.parent / "golden_cases.json"))["cases"]
    tp = fn = 0
    plans, profiles = {}, {}
    for case in cases:
        if case["adversarial"]:
            continue
        pid = case["patientId"]
        summary = client.FetchPatientSummary(pid)
        scored = assess_improved(pid, summary)
        c = scorers.score_against_human(scored, case["human_label"])["_counts"]
        tp += c["tp"]
        fn += c["fn"]
        plans[pid] = draft_care_plan_improved(pid, scored)
        profiles[pid] = tuple(sorted(
            k for k, v in scorers.parse_assessment(scored)["domains"].items()
            if v == "HIGH" and k in scorers.PLAN_DOMAINS
        ))

    assert round(tp / (tp + fn), 3) == 1.0
    assert scorers.score_care_plan_differentiation(plans, profiles)["passed"] is True

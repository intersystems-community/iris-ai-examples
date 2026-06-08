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
    """The shipped rule under-calls real needs: recall < 1, precision == 1."""
    s = _report()["summary"]
    assert s["human_truth_micro_recall"] == 0.75
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

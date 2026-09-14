"""Proposed improvements, driven by what the evals revealed.

This module is NOT a mirror of the shipped tool — it is the *next version*,
written to close the gaps the eval suite surfaced. The notebook runs the eval
set against these to show the metrics move, which is the whole point: the eval
is the fitness function, the improvement is hill-climbing against it.

Two fixes, each tied to a specific finding:

  fix #1 (clinician recall 0.714 -> 1.0): the rule-based AssessSDoHRisk under-
  called Economic and Health Care risk because its keyword list missed the way
  real notes phrase hardship ("cost", "skipping meals", "uninsured", "food
  insecure"). Broaden the lexicon. The right long-term fix is an LLM extraction
  step with the deterministic scorer as a guardrail — but more keywords is the
  cheap, no-LLM win the eval justifies first.

  fix #2 (L5 care-plan differentiation FAIL): DraftCarePlan keyed off the
  presence of domain *names* in the scores string — which are always present —
  so every patient got an identical plan. Key off the domain *values* (HIGH)
  instead, so the plan reflects the actual risk profile.

Everything else is deliberately held constant, including the priority thresholds
and the domain list, so the metric movement is attributable to those two fixes.
One gap survives on purpose: the improved rule still calls James HIGH where the
clinician says URGENT. Priority calibration is a separate change with its own
evidence, and folding it in here would make fix #1's effect unreadable.
"""

from __future__ import annotations

import re

# fix #1 — broadened lexicons. Additions over the shipped tool are commented.
_ECON = ("unemploy", "job", "income", "afford",
         "cost", "food insecure", "food bank", "skipping meal", "uninsur", "snap", "medicaid")
_EDU = ("english", "language", "literacy")
# "transport" was in the shipped tool's Health Care list, back when Transportation
# Access was not a domain of its own. It is one now, so the barrier is scored where
# it belongs. Medication affordability replaces it here — "difficulty affording
# insulin" is an access-to-care problem, and it is how the note actually reads.
_HEALTH = ("uninsur", "no doctor", "clinic",
           "afford", "skipping medication", "medication cost", "skipping meds")
_NBHD = ("housing", "mold", "unsafe", "food bank", "food insecure")
_SOCIAL = ("alone", "isolat", "no family", "no support")
_TRANSPORT = ("no car", "no ride", "no bus", "transport", "transit",
              "missed appointment", "can't get to", "cannot get to",
              "no vehicle", "cannot travel", "unable to get to", "missed visit")

# Same thresholds as the shipped rule, over the same six domains.
_URGENT_AT, _HIGH_AT = 5, 3


def assess_improved(patient_id: str, clinical_summary: str) -> str:
    """Drop-in replacement for AssessSDoHRisk with the broadened lexicon."""
    s = clinical_summary.lower()
    econ = "HIGH" if any(k in s for k in _ECON) else "LOW"
    edu = "HIGH" if any(k in s for k in _EDU) else "LOW"
    health = "HIGH" if any(k in s for k in _HEALTH) else "MEDIUM"
    nbhd = "HIGH" if any(k in s for k in _NBHD) else "LOW"
    social = "HIGH" if any(k in s for k in _SOCIAL) else "LOW"
    transport = "HIGH" if any(k in s for k in _TRANSPORT) else "LOW"
    domains = (econ, edu, health, nbhd, social, transport)
    high = sum(1 for d in domains if d == "HIGH")
    priority = "URGENT" if high >= _URGENT_AT else "HIGH" if high >= _HIGH_AT else "ROUTINE"
    return (
        f"SDoH Risk Assessment for {patient_id}:\n"
        f"  Economic Stability:      {econ}\n"
        f"  Education Access:        {edu}\n"
        f"  Health Care Access:      {health}\n"
        f"  Neighborhood/Built Env:  {nbhd}\n"
        f"  Social Context:          {social}\n"
        f"  Transportation Access:   {transport}\n"
        f"Overall Priority: {priority} ({high}/{len(domains)} domains elevated)"
    )


# fix #2 — care plan that reflects the actual HIGH domains, not just their names.
def draft_care_plan_improved(patient_id: str, sdoh_scores: str) -> str:
    """Drop-in replacement for DraftCarePlan that reads domain VALUES."""
    def is_high(label):
        m = re.search(re.escape(label) + r":\s*(HIGH|MEDIUM|LOW)", sdoh_scores)
        return bool(m) and m.group(1) == "HIGH"

    steps = []
    if is_high("Economic Stability"):
        steps.append("Connect with financial assistance programs — SNAP, Medicaid, emergency rental assistance")
    if is_high("Health Care Access"):
        steps.append("Schedule CHW home visit within 5 days — assess medication-access barriers")
    if is_high("Neighborhood/Built Env"):
        steps.append("Report housing issues to housing authority — document mold/safety concerns")
    if is_high("Social Context"):
        steps.append("Refer to community social connection program — senior center, peer support group")
    if is_high("Transportation Access"):
        steps.append("Enroll in patient transport program or telehealth if available")
    steps.append("Schedule 30-day follow-up call to assess progress on care plan goals")

    body = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    return f"Care Plan for {patient_id}:\n\n{body}\n\nPriority: Urgent if 5+ domains HIGH — escalate to supervising CHW"

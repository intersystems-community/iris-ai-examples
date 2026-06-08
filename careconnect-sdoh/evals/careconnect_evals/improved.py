"""Proposed improvements, driven by what the evals revealed.

This module is NOT a mirror of the shipped tool — it is the *next version*,
written to close the gaps the eval suite surfaced. The notebook runs the eval
set against these to show the metrics move, which is the whole point: the eval
is the fitness function, the improvement is hill-climbing against it.

Two fixes, each tied to a specific finding:

  fix #1 (clinician recall 0.75 -> 1.0): the rule-based AssessSDoHRisk under-
  called Economic and Health Care risk because its keyword list missed the way
  real notes phrase hardship ("cost", "skipping meals", "uninsured", "food
  insecure"). Broaden the lexicon. The right long-term fix is an LLM extraction
  step with the deterministic scorer as a guardrail — but more keywords is the
  cheap, no-LLM win the eval justifies first.

  fix #2 (L5 care-plan differentiation FAIL): DraftCarePlan keyed off the
  presence of domain *names* in the scores string — which are always present —
  so every patient got an identical plan. Key off the domain *values* (HIGH)
  instead, so the plan reflects the actual risk profile.
"""

from __future__ import annotations

import re

# fix #1 — broadened lexicons. Additions over the shipped tool are commented.
_ECON = ("unemploy", "job", "income", "afford",
         "cost", "food insecure", "food bank", "skipping meal", "uninsur", "snap", "medicaid")
_EDU = ("english", "language", "literacy")
_HEALTH = ("uninsur", "transport", "no doctor", "clinic",
           "skipping medication", "medication cost", "skipping meds")
_NBHD = ("housing", "mold", "unsafe", "food bank", "food insecure")
_SOCIAL = ("alone", "isolat", "no family", "no support")


def assess_improved(patient_id: str, clinical_summary: str) -> str:
    """Drop-in replacement for AssessSDoHRisk with the broadened lexicon."""
    s = clinical_summary.lower()
    econ = "HIGH" if any(k in s for k in _ECON) else "LOW"
    edu = "HIGH" if any(k in s for k in _EDU) else "LOW"
    health = "HIGH" if any(k in s for k in _HEALTH) else "MEDIUM"
    nbhd = "HIGH" if any(k in s for k in _NBHD) else "LOW"
    social = "HIGH" if any(k in s for k in _SOCIAL) else "LOW"
    high = sum(1 for d in (econ, edu, health, nbhd, social) if d == "HIGH")
    priority = "URGENT" if high >= 4 else "HIGH" if high >= 2 else "ROUTINE"
    return (
        f"SDoH Risk Assessment for {patient_id}:\n"
        f"  Economic Stability:      {econ}\n"
        f"  Education Access:        {edu}\n"
        f"  Health Care Access:      {health}\n"
        f"  Neighborhood/Built Env:  {nbhd}\n"
        f"  Social Context:          {social}\n"
        f"Overall Priority: {priority} ({high}/5 domains elevated)"
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
        steps.append("Schedule CHW home visit within 5 days — assess transportation and medication-access barriers")
        steps.append("Enroll in patient transport program or telehealth if available")
    if is_high("Neighborhood/Built Env"):
        steps.append("Report housing issues to housing authority — document mold/safety concerns")
    if is_high("Social Context"):
        steps.append("Refer to community social connection program — senior center, peer support group")
    steps.append("Schedule 30-day follow-up call to assess progress on care plan goals")

    body = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    return f"Care Plan for {patient_id}:\n\n{body}\n\nPriority: Urgent if 4+ domains HIGH — escalate to supervising CHW"

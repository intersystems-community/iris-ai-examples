"""Eval harness: load golden cases, run the agent, score every layer, report.

This is the orchestration the runner and the notebook both call. It returns a
plain dict so it's trivial to serialize, diff between runs, or chart.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import scorers
from .providers import get_provider
from .tools_local import PATIENTS

_DEFAULT_CASES = Path(__file__).resolve().parent.parent / "golden_cases.json"


def load_cases(path: str | os.PathLike | None = None) -> list:
    path = Path(path) if path else _DEFAULT_CASES
    return json.loads(path.read_text())["cases"]


def run_case(provider, case: dict) -> dict:
    """Run one case through the agent and score all per-case layers."""
    run = provider.run_agent(case)
    assessment = run.last_result("AssessSDoHRisk")
    care_plan = run.last_result("DraftCarePlan")
    note = PATIENTS.get(case["patientId"], {}).get("Notes", "")

    layers = {
        "L1_rule_regression": scorers.score_rule_regression(assessment, case["rule_expected"]),
        "L1b_vs_human": scorers.score_against_human(assessment, case["human_label"]),
        "L2_trajectory": scorers.score_trajectory(
            run.tool_names(), case["expected_trajectory"], case["expect_followup"]
        ),
        "L3_outcome": scorers.score_outcome(run, case["patientId"], case["expect_followup"]),
        "L4_quality": scorers.score_quality(provider, run.final_text, note),
    }
    high_domains = {
        k for k, v in scorers.parse_assessment(assessment)["domains"].items()
        if v == "HIGH" and k in scorers.PLAN_DOMAINS
    }
    return {
        "id": case["id"],
        "patientId": case["patientId"],
        "tags": case.get("tags", []),
        "adversarial": case.get("adversarial", False),
        "profile_key": tuple(sorted(high_domains)),
        "error": run.error,
        "tool_trajectory": run.tool_names(),
        "final_text": run.final_text,
        "care_plan": care_plan,
        "layers": layers,
    }


def run_suite(provider_name: str | None = None, cases_path: str | None = None) -> dict:
    """Run every case, plus the cross-case differentiation check, and aggregate."""
    provider = get_provider(provider_name)
    cases = load_cases(cases_path)
    results = [run_case(provider, c) for c in cases]

    # Layer 5: do patients with different risk profiles get different plans?
    # Take one (non-adversarial) result per patient, with its elevated-domain
    # profile so the metric only flags identical-plan/different-needs pairs.
    plans, profiles = {}, {}
    for r in results:
        if r["adversarial"] or r["patientId"] in plans:
            continue
        plans[r["patientId"]] = r["care_plan"]
        profiles[r["patientId"]] = r["profile_key"]
    differentiation = scorers.score_care_plan_differentiation(plans, profiles)

    per_layer_pass = {}
    for layer in ("L1_rule_regression", "L2_trajectory", "L3_outcome", "L4_quality"):
        passed = sum(1 for r in results if r["layers"][layer]["passed"])
        per_layer_pass[layer] = {"passed": passed, "total": len(results)}

    # Micro-average the human-truth recall over realistic (non-adversarial)
    # inputs — this measures the rule's clinical sensitivity. Adversarial
    # paraphrase misses are already captured as L1 regressions, so folding them
    # in here would conflate two different root causes.
    clinical = [r for r in results if not r["adversarial"]]
    tp = sum(r["layers"]["L1b_vs_human"]["_counts"]["tp"] for r in clinical)
    fn = sum(r["layers"]["L1b_vs_human"]["_counts"]["fn"] for r in clinical)
    fp = sum(r["layers"]["L1b_vs_human"]["_counts"]["fp"] for r in clinical)
    micro_recall = round(tp / (tp + fn), 3) if (tp + fn) else 1.0
    micro_precision = round(tp / (tp + fp), 3) if (tp + fp) else 1.0

    return {
        "provider": provider.name,
        "model": getattr(provider, "model", None),
        "n_cases": len(results),
        "results": results,
        "summary": {
            "per_layer": per_layer_pass,
            "care_plan_differentiation": differentiation,
            "human_truth_micro_recall": micro_recall,
            "human_truth_micro_precision": micro_precision,
        },
    }


# --- pretty console report ---------------------------------------------------

_GREEN, _RED, _YELLOW, _DIM, _RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"


def _mark(ok: bool) -> str:
    return f"{_GREEN}PASS{_RESET}" if ok else f"{_RED}FAIL{_RESET}"


def print_report(report: dict) -> None:
    s = report["summary"]
    print(f"\nCareConnect SDoH Agent — Eval Report")
    print(f"provider={report['provider']} model={report['model']} cases={report['n_cases']}\n")
    print(f"{'CASE':<32} {'L1 rule':<9} {'L2 traj':<9} {'L3 out':<9} {'L4 qual':<9} recall")
    print("-" * 84)
    for r in report["results"]:
        L = r["layers"]
        rec = L["L1b_vs_human"]["recall"]
        tag = f" {_YELLOW}[adversarial]{_RESET}" if r["adversarial"] else ""
        print(
            f"{r['id']:<32} "
            f"{_mark(L['L1_rule_regression']['passed']):<18} "
            f"{_mark(L['L2_trajectory']['passed']):<18} "
            f"{_mark(L['L3_outcome']['passed']):<18} "
            f"{_mark(L['L4_quality']['passed']):<18} "
            f"{rec:>5}{tag}"
        )
        if r["error"]:
            print(f"  {_RED}error: {r['error']}{_RESET}")

    print("\nLayer pass rates:")
    for layer, v in s["per_layer"].items():
        print(f"  {layer:<22} {v['passed']}/{v['total']}")

    d = s["care_plan_differentiation"]
    print(
        f"\nL5 care-plan differentiation: {_mark(d['passed'])} "
        f"({d['distinct_plans']} distinct plan(s) across {d['patients_compared']} patients)"
        + (f" {_RED}— ALL IDENTICAL{_RESET}" if d["all_identical"] else "")
    )
    print(
        f"\nClinician-truth micro recall:    {s['human_truth_micro_recall']} "
        f"{_DIM}(fraction of genuinely elevated domains the system flags){_RESET}"
    )
    print(f"Clinician-truth micro precision: {s['human_truth_micro_precision']}\n")

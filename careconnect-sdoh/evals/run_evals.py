#!/usr/bin/env python3
"""CLI entry point for the CareConnect SDoH agent evals.

    # offline, no key — the default; runs instantly and deterministically
    python run_evals.py

    # against a real model (provider-agnostic)
    CARECONNECT_EVAL_PROVIDER=anthropic ANTHROPIC_API_KEY=...  python run_evals.py
    CARECONNECT_EVAL_PROVIDER=openai    OPENAI_API_KEY=...      python run_evals.py

Exit code is non-zero if any regression-style layer (L1 rule, L2 trajectory,
L3 outcome) fails, so this drops straight into CI as a gate on prompt/tool changes.
"""

from __future__ import annotations

import argparse
import json
import sys

from careconnect_evals import print_report, run_suite


def main() -> int:
    ap = argparse.ArgumentParser(description="Run CareConnect SDoH agent evals.")
    ap.add_argument("--provider", default=None, help="mock | anthropic | openai (env: CARECONNECT_EVAL_PROVIDER)")
    ap.add_argument("--cases", default=None, help="path to a golden_cases.json")
    ap.add_argument("--json", dest="json_out", default=None, help="write full report JSON here")
    args = ap.parse_args()

    report = run_suite(args.provider, args.cases)
    print_report(report)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Full report written to {args.json_out}")

    # Gate on the deterministic/regression layers (not L4 judge — that's advisory).
    gate_layers = ("L1_rule_regression", "L2_trajectory", "L3_outcome")
    regressions = sum(
        1
        for r in report["results"]
        for layer in gate_layers
        if not r["layers"][layer]["passed"]
    )
    if regressions:
        print(f"{regressions} regression-layer failure(s) — see report above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""CareConnect SDoH agent evaluation harness.

A small, provider-agnostic evals suite for the careconnect-sdoh example. See
EVALS.md for the lessons it's built to demonstrate.
"""

from .harness import load_cases, print_report, run_case, run_suite

__all__ = ["run_suite", "run_case", "load_cases", "print_report"]

#!/usr/bin/env python3
"""CLI entry point for the offline test suite, matching the
careconnect-sdoh/evals model (no Docker, no API key, no network):

    python run_tests.py

Exit code is pytest's own: non-zero on any failure, so this drops straight
into CI as a gate on the DDL/URL/partitioning builders.
"""

import sys

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", "tests/"]))

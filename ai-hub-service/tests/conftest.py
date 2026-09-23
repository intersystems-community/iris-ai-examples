"""Shared fixtures. Nothing here needs Docker, IRIS, a network, or an API key."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXAMPLES = ROOT / "examples" / "careconnect"
# Paths live here rather than in test modules: the repo hygiene guard reads any
# "careconnect-..." / "ai-hub-..." string in a test module as a container name.
CARECONNECT_SDOH = ROOT.parent / "careconnect-sdoh"
EVALS = CARECONNECT_SDOH / "evals"
# Where the Dockerfile puts this directory inside the service image.
IMAGE_ROOT = "/app/ai-hub-service/"

for p in (ROOT / "src", EXAMPLES, EVALS, HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from aihub_service.app import create_app  # noqa: E402

CHW = {"Authorization": "Bearer dev-chw-key"}
LEAD = {"Authorization": "Bearer dev-lead-key"}
APP = {"X-API-Key": "dev-app-key"}
ADMIN = {"Authorization": "Bearer dev-admin-key"}


@pytest.fixture
def offline():
    """The offline CareConnect service, fresh per test (its simulated
    production and run store start empty)."""
    return TestClient(create_app(EXAMPLES / "offline.yaml"))

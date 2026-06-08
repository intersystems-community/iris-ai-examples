"""Parity check: the Python tool port vs the live ObjectScript tools.

The harness runs offline against tools_local.py, a hand-written Python mirror of
CareConnect.Tools.SDoHToolSet. A mirror that drifts from the real thing makes
the whole eval a lie — so this test calls the actual ObjectScript classmethods
in a running IRIS and asserts byte-identical output for the deterministic tools.

SKIPPED automatically unless a reachable IRIS is configured. Bring the stack up
(`cd ../docker && docker compose up -d`), then:

    IRIS_HOST=localhost IRIS_PORT=1972 IRIS_NAMESPACE=USER \
    IRIS_USER=_SYSTEM IRIS_PASSWORD=SYS  python -m pytest tests/test_parity.py
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careconnect_evals.tools_local import LocalToolClient, PATIENTS  # noqa: E402

iris = pytest.importorskip("iris", reason="intersystems-irispython not installed")


@pytest.fixture(scope="module")
def live():
    host = os.getenv("IRIS_HOST")
    if not host:
        pytest.skip("Set IRIS_HOST/IRIS_PORT/... to run live parity checks")
    conn = iris.connect(
        host,
        int(os.getenv("IRIS_PORT", "1972")),
        os.getenv("IRIS_NAMESPACE", "USER"),
        os.getenv("IRIS_USER", "_SYSTEM"),
        os.getenv("IRIS_PASSWORD", "SYS"),
    )
    yield iris.createIRIS(conn)
    conn.close()


CLS = "CareConnect.Tools.SDoHToolSet"


@pytest.mark.parametrize("pid", list(PATIENTS))
def test_fetch_patient_summary_parity(live, pid):
    local = LocalToolClient().FetchPatientSummary(pid)
    remote = live.classMethodString(CLS, "FetchPatientSummary", pid, "90")
    assert local == remote


@pytest.mark.parametrize("pid", list(PATIENTS))
def test_assess_risk_parity(live, pid):
    summary = LocalToolClient().FetchPatientSummary(pid)
    local = LocalToolClient().AssessSDoHRisk(pid, summary, "")
    remote = live.classMethodString(CLS, "AssessSDoHRisk", pid, summary, "")
    assert local == remote


@pytest.mark.parametrize("pid", list(PATIENTS))
def test_draft_care_plan_parity(live, pid):
    summary = LocalToolClient().FetchPatientSummary(pid)
    scores = LocalToolClient().AssessSDoHRisk(pid, summary, "")
    local = LocalToolClient().DraftCarePlan(pid, scores)
    remote = live.classMethodString(CLS, "DraftCarePlan", pid, scores)
    assert local == remote

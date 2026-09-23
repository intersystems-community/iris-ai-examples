"""One agent, three topologies, one answer.

The claim the service makes is that where a tool runs is a deployment detail.
These tests hold it to that for CareConnect: the same playbook, for each demo
patient, run

    offline   every tool in-process (the eval suite's port of SDoHToolSet)
    inplace   every tool over MCP from one AI Hub IRIS
    sidecar   patient data and interop from a legacy IRIS over SQL and the
              Native API; scoring and care planning from an AI Hub companion
              over MCP

must produce the same tool sequence, the same tool outputs and the same final
answer — up to the follow-up's job id, which is a fresh GUID each time.

What stands in for IRIS here: the MCP endpoint is FakeMCPServer in front of the
offline port, and the legacy instance is FakeLegacyIRIS, whose SQL runs for
real on SQLite against columns read from Patient.cls. The service's routing,
bindings, SQL and formatters are the real ones.
"""

from __future__ import annotations

import re

import pytest
from careconnect_evals.tools_local import PATIENTS, TOOL_SCHEMAS, LocalToolClient
from conftest import CHW, EXAMPLES, LEAD
from fakes import FakeLegacyIRIS, FakeMCPServer
from fastapi.testclient import TestClient

import careconnect_bindings
from aihub_service.app import create_app

JOB = re.compile(r"jobId=[0-9A-F-]{36}")


def _normalize(text: str) -> str:
    return JOB.sub("jobId=<guid>", text)


def offline_client():
    return TestClient(create_app(EXAMPLES / "offline.yaml")), None


def inplace_client():
    hub = FakeMCPServer(LocalToolClient(production_running=True), TOOL_SCHEMAS)
    return TestClient(create_app(EXAMPLES / "inplace.yaml", http_transport=hub.transport())), hub


def sidecar_client(sse=True):
    legacy = FakeLegacyIRIS(PATIENTS)
    companion = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS, sse=sse)
    app = create_app(EXAMPLES / "sidecar.yaml", http_transport=companion.transport(),
                     iris_connect=legacy.connect)
    return TestClient(app), (legacy, companion)


MODES = {"offline": offline_client, "inplace": inplace_client, "sidecar": sidecar_client}


def assess(client, patient_id, **context):
    r = client.post("/v1/agents/sdoh-assessment/runs", headers=CHW,
                    json={"context": {"patientId": patient_id, **context}}).json()
    if r["status"] == "awaiting_approval":
        r = client.post(f"/v1/runs/{r['id']}/approval", headers=LEAD,
                        json={"decision": "approve"}).json()
    return r


def comparable(run: dict) -> dict:
    steps = []
    for s in run["steps"]:
        out = _normalize(s["output"])
        if s["tool"] == "GetInteropTraces":
            # Trace rows carry each instance's own IDs and timestamps; the
            # count and the route are what the answer depends on.
            out = out.splitlines()[0]
        steps.append((s["tool"], s["args"], out))
    return {"status": run["status"], "steps": steps, "output": _normalize(run["output"])}


@pytest.mark.parametrize("patient_id", sorted(PATIENTS))
def test_the_three_modes_give_the_same_answer(patient_id):
    results = {}
    for mode, make in MODES.items():
        client, _ = make()
        results[mode] = comparable(assess(client, patient_id))
    assert results["inplace"] == results["offline"]
    assert results["sidecar"] == results["offline"]


def test_sidecar_really_routes_to_both_instances():
    client, (legacy, companion) = sidecar_client()
    run = assess(client, "maria-gonzalez-001")
    backends = {s["tool"]: s["backend"] for s in run["steps"]}
    assert backends == {
        "FetchPatientSummary": "legacy",
        "SearchSDoHProtocols": "companion",
        "AssessSDoHRisk": "companion",
        "DraftCarePlan": "companion",
        "TriggerFollowUp": "legacy",
        "GetInteropTraces": "legacy",
    }
    called = [c["msg"]["params"]["name"] for c in companion.requests if c["msg"].get("method") == "tools/call"]
    assert called == ["SearchSDoHProtocols", "AssessSDoHRisk", "DraftCarePlan"]
    # The follow-up reached the legacy production through the allow-listed dispatcher.
    cls, method, args = legacy.calls[0]
    assert (cls, method) == ("AIHub.Legacy.Interop", "Dispatch")
    assert args[:2] == ("CareConnect.Service.SDoHFollowUpBS", "CareConnect.Message.FollowUpRequest")
    assert legacy.last_request == {"PatientId": "maria-gonzalez-001", "Priority": "urgent", "SDoHFlags": ""}


def test_sidecar_follow_up_waits_for_approval_before_touching_the_legacy_production():
    client, (legacy, _) = sidecar_client()
    r = client.post("/v1/agents/sdoh-assessment/runs", headers=CHW,
                    json={"context": {"patientId": "maria-gonzalez-001"}}).json()
    assert r["status"] == "awaiting_approval"
    assert legacy.calls == [], "the interop dispatcher ran before anyone approved"


def test_sidecar_reports_a_stopped_legacy_production_as_the_toolset_does():
    client, (legacy, _) = sidecar_client()
    legacy.running = False
    run = assess(client, "maria-gonzalez-001")
    follow = next(s for s in run["steps"] if s["tool"] == "TriggerFollowUp")
    assert follow["output"] == LocalToolClient(production_running=False).TriggerFollowUp("x")


# -- the legacy formatters, byte for byte against the port -----------------
#
# careconnect-sdoh's parity tests hold the port to the ObjectScript; these hold
# the sidecar's SQL + formatter route to the port. Together: legacy SQL output
# equals what SDoHToolSet prints.


def _legacy_tool(name, **args):
    client, _ = sidecar_client()
    return client.post(f"/v1/tools/{name}/invoke", headers=CHW, json={"args": args}).json()["output"]


@pytest.mark.parametrize("args", [
    {},
    {"query": "maria"},
    {"query": "HEART"},
    {"query": "sarah-kim-003"},
    {"query": "nobody"},
])
def test_search_patients_over_sql_matches_the_toolset(args):
    assert _legacy_tool("SearchPatients", **args) == LocalToolClient().SearchPatients(**args)


@pytest.mark.parametrize("patient_id", [*sorted(PATIENTS), "no-such-patient", ""])
def test_patient_summary_over_sql_matches_the_toolset(patient_id):
    assert _legacy_tool("FetchPatientSummary", patientId=patient_id) == \
        LocalToolClient().FetchPatientSummary(patient_id)


def test_trace_formatter_matches_the_objectscript_layout():
    rows = [{"ID": 7, "TimeCreated": "2026-09-23 12:00:00",
             "SourceConfigName": "CareConnect.Service.SDoHFollowUpBS",
             "TargetConfigName": "CareConnect.Process.SDoHFollowUpBP",
             "MessageBodyClassName": "CareConnect.Message.FollowUpRequest", "Status": 9}]
    assert careconnect_bindings.interop_traces(rows, {}) == (
        "Interoperability Traces (1):\n"
        "[7] 2026-09-23 12:00:00 | SDoHFollowUpBS -> SDoHFollowUpBP | FollowUpRequest | Completed\n"
    )


def test_a_forbidden_dispatch_is_an_error_not_a_follow_up():
    assert careconnect_bindings.follow_up('{"status":"forbidden","error":"not allowed"}',
                                          {"patientId": "p"}).startswith("ERROR")

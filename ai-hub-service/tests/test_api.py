"""The HTTP contract, driven against the offline CareConnect service.

These are the behaviours a calling application relies on: who may call what,
what a run looks like, how the approval gate parks and resumes a run, and what
lands in the audit trail.
"""

from __future__ import annotations

import time

import httpx
from conftest import ADMIN, APP, CHW, EXAMPLES, LEAD
from fastapi.testclient import TestClient

from aihub_service.app import create_app
from aihub_service.config import load_config

MARIA = {"patientId": "maria-gonzalez-001"}  # URGENT: 5 of 6 domains HIGH
JAMES = {"patientId": "james-okafor-002"}  # ROUTINE: 2 of 6
SARAH = {"patientId": "sarah-kim-003"}  # HIGH: 3 of 6


def run(client, context, headers=CHW, agent="sdoh-assessment", **extra):
    r = client.post(f"/v1/agents/{agent}/runs", headers=headers, json={"context": context, **extra})
    assert r.status_code in (200, 202), r.text
    return r.json()


# -- health and discovery --------------------------------------------------


def test_health_needs_no_key(offline):
    assert offline.get("/healthz").json()["status"] == "ok"
    ready = offline.get("/readyz")
    assert ready.status_code == 200 and ready.json()["ready"] is True


def test_every_v1_route_needs_a_key(offline):
    for path in ("/v1/service", "/v1/tools", "/v1/agents", "/v1/runs", "/v1/audit"):
        assert offline.get(path).status_code == 401, path
        assert offline.get(path, headers={"Authorization": "Bearer nope"}).status_code == 401, path


def test_service_reports_mode_and_principal(offline):
    info = offline.get("/v1/service", headers=CHW).json()
    assert info["mode"] == "offline"
    assert info["backends"] == {"local": "python"}
    assert info["principal"] == {"name": "chw_user", "roles": ["caller"]}


def test_catalog_lists_the_ten_core_tools_with_schemas_from_the_backend(offline):
    tools = {t["name"]: t for t in offline.get("/v1/tools", headers=CHW).json()["tools"]}
    assert len(tools) == 10
    assert tools["AssessSDoHRisk"]["description"].startswith("Score a patient on six SDoH domains")
    assert tools["FetchPatientSummary"]["parameters"]["required"] == ["patientId"]
    assert {n for n, t in tools.items() if t["effect"] == "write"} == {"TriggerFollowUp", "StartProduction"}


def test_agent_listing_says_which_tools_are_gated(offline):
    agent = offline.get("/v1/agents/sdoh-assessment", headers=CHW).json()
    gated = {t["name"] for t in agent["tools"] if t["requires_approval"]}
    assert gated == {"TriggerFollowUp"}
    assert agent["requires"] == ["patientId"]


# -- direct tool calls -----------------------------------------------------


def test_read_tool_invocation_returns_the_tool_text(offline):
    r = offline.post("/v1/tools/SearchPatients/invoke", headers=APP, json={"args": {"query": "maria"}})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True and body["backend"] == "local"
    assert "patientId: maria-gonzalez-001" in body["output"]


def test_write_tool_invocation_is_admin_only(offline):
    args = {"args": {"patientId": "maria-gonzalez-001"}}
    assert offline.post("/v1/tools/TriggerFollowUp/invoke", headers=CHW, json=args).status_code == 403
    assert offline.post("/v1/tools/TriggerFollowUp/invoke", headers=LEAD, json=args).status_code == 403
    r = offline.post("/v1/tools/TriggerFollowUp/invoke", headers=ADMIN, json=args)
    assert r.status_code == 200 and "Follow-up triggered for maria-gonzalez-001" in r.json()["output"]


def test_tool_errors_come_back_as_not_ok(offline):
    r = offline.post("/v1/tools/FetchPatientSummary/invoke", headers=CHW, json={"args": {"patientId": ""}})
    assert r.json() == {**r.json(), "ok": False, "output": "ERROR: patientId is required"}


def test_unknown_tool_is_404(offline):
    assert offline.post("/v1/tools/Nope/invoke", headers=CHW, json={}).status_code == 404


# -- playbook runs and the approval gate -----------------------------------


def test_routine_case_runs_to_completion_without_a_follow_up(offline):
    r = run(offline, JAMES)
    assert r["status"] == "succeeded"
    assert [s["tool"] for s in r["steps"]] == [
        "FetchPatientSummary", "SearchSDoHProtocols", "AssessSDoHRisk", "DraftCarePlan",
    ]
    assert "Overall Priority: ROUTINE (2/6 domains elevated)" in r["output"]
    assert r["output"].endswith("Follow-up: not triggered")


def test_urgent_case_parks_on_the_follow_up(offline):
    r = run(offline, MARIA)
    assert r["status"] == "awaiting_approval"
    pending = r["awaiting_approval"]
    assert pending["tool"] == "TriggerFollowUp" and pending["effect"] == "write"
    assert pending["args"] == {"patientId": "maria-gonzalez-001", "priority": "urgent", "sdohFlags": ""}
    # Nothing has fired: the interop tool has not run.
    assert "TriggerFollowUp" not in [s["tool"] for s in r["steps"]]


def test_approval_resumes_the_run_and_records_the_approver(offline):
    parked = run(offline, MARIA)
    r = offline.post(f"/v1/runs/{parked['id']}/approval", headers=LEAD,
                     json={"decision": "approve", "reason": "URGENT; CHW visit this week"}).json()
    assert r["status"] == "succeeded"
    steps = {s["tool"]: s for s in r["steps"]}
    assert steps["TriggerFollowUp"]["decided_by"] == "clinical_lead"
    assert steps["TriggerFollowUp"]["output"].startswith("Follow-up triggered for maria-gonzalez-001 (priority=urgent)")
    assert steps["GetInteropTraces"]["output"].startswith("Interoperability Traces (4):")
    decided = next(e for e in r["events"] if e["type"] == "approval_decided")
    assert decided["by"] == "clinical_lead" and decided["reason"] == "URGENT; CHW visit this week"


def test_rejection_skips_the_action_and_the_run_still_answers(offline):
    parked = run(offline, MARIA)
    r = offline.post(f"/v1/runs/{parked['id']}/approval", headers=LEAD,
                     json={"decision": "reject", "reason": "family already engaged"}).json()
    assert r["status"] == "succeeded"
    follow = next(s for s in r["steps"] if s["tool"] == "TriggerFollowUp")
    assert follow["status"] == "rejected" and follow["ok"] is False
    assert follow["output"].startswith("REJECTED by clinical_lead: family already engaged")
    # Nothing reached the production, so there is no trace step either.
    assert [s["tool"] for s in r["steps"]][-1] == "TriggerFollowUp"
    assert "Follow-up: REJECTED by clinical_lead" in r["output"]


def test_a_caller_cannot_approve_and_nobody_approves_their_own_run(offline):
    parked = run(offline, MARIA, headers=LEAD)
    body = {"decision": "approve"}
    assert offline.post(f"/v1/runs/{parked['id']}/approval", headers=CHW, json=body).status_code == 403
    assert offline.post(f"/v1/runs/{parked['id']}/approval", headers=LEAD, json=body).status_code == 403
    assert offline.post(f"/v1/runs/{parked['id']}/approval", headers=ADMIN, json=body).json()["status"] == "succeeded"


def test_deciding_a_run_that_is_not_parked_is_409(offline):
    done = run(offline, JAMES)
    r = offline.post(f"/v1/runs/{done['id']}/approval", headers=LEAD, json={"decision": "approve"})
    assert r.status_code == 409


def test_follow_up_on_request_uses_the_callers_priority(offline):
    parked = run(offline, {**SARAH, "followUp": True, "priority": "high"})
    assert parked["awaiting_approval"]["args"]["priority"] == "high"


def test_playbook_requirements_are_checked_before_the_run_starts(offline):
    r = offline.post("/v1/agents/sdoh-assessment/runs", headers=CHW, json={"context": {}})
    assert r.status_code == 422 and "context.patientId is required" in r.json()["detail"]


# -- visibility, queue, cancel, audit --------------------------------------


def test_callers_see_their_own_runs_and_approvers_see_the_queue(offline):
    mine = run(offline, MARIA, headers=CHW)
    other = run(offline, MARIA, headers=APP)
    assert offline.get(f"/v1/runs/{other['id']}", headers=CHW).status_code == 404
    assert {r["id"] for r in offline.get("/v1/runs", headers=CHW).json()["runs"]} == {mine["id"]}
    queue = offline.get("/v1/runs?status=awaiting_approval", headers=LEAD).json()["runs"]
    assert {r["id"] for r in queue} == {mine["id"], other["id"]}


def test_cancel_a_parked_run(offline):
    parked = run(offline, MARIA)
    r = offline.post(f"/v1/runs/{parked['id']}/cancel", headers=CHW).json()
    assert r["status"] == "cancelled" and r["awaiting_approval"] is None
    assert offline.post(f"/v1/runs/{parked['id']}/cancel", headers=CHW).status_code == 409


def test_every_tool_call_is_audited_with_its_principal(offline):
    offline.post("/v1/tools/SearchPatients/invoke", headers=APP, json={"args": {}})
    run(offline, JAMES)
    assert offline.get("/v1/audit", headers=CHW).status_code == 403
    entries = offline.get("/v1/audit", headers=LEAD).json()["entries"]
    assert entries[0]["principal"] == "careconnect_app" and entries[0]["run_id"] is None
    assert [e["tool"] for e in entries[1:]] == [
        "FetchPatientSummary", "SearchSDoHProtocols", "AssessSDoHRisk", "DraftCarePlan",
    ]
    assert {e["run_id"] for e in entries[1:]} != {None}


# -- async runs and callbacks ----------------------------------------------


def test_an_async_run_is_polled_to_its_settled_state(offline):
    r = offline.post("/v1/agents/sdoh-assessment/runs", headers=CHW,
                     json={"context": JAMES, "wait": False})
    assert r.status_code == 202
    for _ in range(100):
        state = offline.get(f"/v1/runs/{r.json()['id']}", headers=CHW).json()
        if state["status"] != "running":
            break
        time.sleep(0.02)
    assert state["status"] == "succeeded"


def test_callbacks_go_only_to_allowed_hosts():
    cfg = load_config(EXAMPLES / "offline.yaml")
    cfg.raw["callbacks"] = {"allowed_hosts": ["legacy-iris"]}
    delivered = []
    transport = httpx.MockTransport(lambda req: delivered.append(req) or httpx.Response(200))
    client = TestClient(create_app(cfg, callback_transport=transport))

    bad = client.post("/v1/agents/sdoh-assessment/runs", headers=CHW,
                      json={"context": JAMES, "callback_url": "https://attacker.example/x"})
    assert bad.status_code == 422

    r = run(client, MARIA, callback_url="http://legacy-iris:52773/csp/aihub/callback")
    assert r["status"] == "awaiting_approval" and len(delivered) == 1
    client.post(f"/v1/runs/{r['id']}/approval", headers=LEAD, json={"decision": "approve"})
    assert len(delivered) == 2
    assert [e["type"] for e in client.get(f"/v1/runs/{r['id']}", headers=CHW).json()["events"]].count(
        "callback_delivered") == 2


def test_the_published_openapi_contract_is_current(offline):
    """openapi.json is the contract callers code against; it must be what the code serves.
    Regenerate with: python -m aihub_service.openapi > openapi.json"""
    import json

    from conftest import ROOT

    published = json.loads((ROOT / "openapi.json").read_text())
    assert offline.get("/openapi.json").json() == published

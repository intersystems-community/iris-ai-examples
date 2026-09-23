"""Model-driven engines, with the model scripted through httpx.MockTransport.

What matters is not that a model is clever but that the service holds the line
around it: a gated call parks the run even when the model asked for it in the
middle of a batch, the conversation survives the pause intact, and a rejected
call is reported back to the model instead of being performed.
"""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import CHW, EXAMPLES, LEAD
from fastapi.testclient import TestClient

from aihub_service.app import create_app
from aihub_service.config import load_config

MARIA = "maria-gonzalez-001"


class ScriptedModel:
    """Replies in order; records every request body the engine sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def transport(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request):
        self.requests.append({"url": str(request.url), "headers": dict(request.headers),
                              "body": json.loads(request.content)})
        return httpx.Response(200, json=self.replies.pop(0))


def openai_call(id, name, **args):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def openai_reply(*calls, content=None):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = list(calls)
    return {"choices": [{"message": msg, "finish_reason": "tool_calls" if calls else "stop"}]}


def anthropic_reply(*blocks, stop="tool_use"):
    return {"content": list(blocks), "stop_reason": stop}


def client_for(engine, model):
    env = {"AIHUB_LLM_ENGINE": engine, "AIHUB_LLM_API_KEY": "test-key",
           "AIHUB_LLM_MODEL": "test-model"}
    cfg = load_config(EXAMPLES / "offline.yaml", environ=env)
    return TestClient(create_app(cfg, http_transport=model.transport()))


def start(client, text):
    return client.post("/v1/agents/sdoh-assistant/runs", headers=CHW,
                       json={"input": text, "context": {"patientId": MARIA}}).json()


def test_openai_loop_runs_tools_and_answers():
    model = ScriptedModel([
        openai_reply(openai_call("c1", "FetchPatientSummary", patientId=MARIA)),
        openai_reply(content="Maria has high social risk."),
    ])
    r = start(client_for("openai", model), "Assess Maria")
    assert r["status"] == "succeeded" and r["output"] == "Maria has high social risk."
    first, second = (q["body"] for q in model.requests)
    assert model.requests[0]["url"].endswith("/v1/chat/completions")
    assert model.requests[0]["headers"]["authorization"] == "Bearer test-key"
    assert first["messages"][0]["role"] == "system"
    assert "Context (JSON)" in first["messages"][1]["content"]
    assert {t["function"]["name"] for t in first["tools"]} >= {"AssessSDoHRisk", "TriggerFollowUp"}
    # The tool result went back paired with its call id.
    tool_msg = second["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert tool_msg["content"].startswith("Patient: Maria Gonzalez, 42F")


def test_a_gated_call_in_a_batch_parks_and_resumes_in_order():
    model = ScriptedModel([
        openai_reply(
            openai_call("c1", "GetProductionStatus"),
            openai_call("c2", "TriggerFollowUp", patientId=MARIA, priority="urgent"),
            openai_call("c3", "GetInteropTraces", maxRows="5"),
        ),
        openai_reply(content="Follow-up is in flight."),
    ])
    client = client_for("openai", model)
    r = start(client, "Trigger a follow-up for Maria")
    assert r["status"] == "awaiting_approval" and r["awaiting_approval"]["id"] == "c2"
    assert [s["tool"] for s in r["steps"]] == ["GetProductionStatus"]
    assert len(model.requests) == 1  # the model is not consulted while parked

    r = client.post(f"/v1/runs/{r['id']}/approval", headers=LEAD, json={"decision": "approve"}).json()
    assert r["status"] == "succeeded"
    assert [s["tool"] for s in r["steps"]] == ["GetProductionStatus", "TriggerFollowUp", "GetInteropTraces"]
    tool_ids = [m["tool_call_id"] for m in model.requests[1]["body"]["messages"] if m["role"] == "tool"]
    assert tool_ids == ["c1", "c2", "c3"]


def test_a_rejected_call_is_reported_to_the_model_not_performed():
    model = ScriptedModel([
        openai_reply(openai_call("c1", "TriggerFollowUp", patientId=MARIA)),
        openai_reply(content="The follow-up was not approved."),
    ])
    client = client_for("openai", model)
    r = start(client, "Trigger a follow-up")
    r = client.post(f"/v1/runs/{r['id']}/approval", headers=LEAD,
                    json={"decision": "reject", "reason": "duplicate referral"}).json()
    told = model.requests[1]["body"]["messages"][-1]["content"]
    assert told.startswith("REJECTED by clinical_lead: duplicate referral")
    assert r["output"] == "The follow-up was not approved."
    audit = client.get("/v1/audit", headers=LEAD).json()["entries"]
    assert "TriggerFollowUp" not in [e["tool"] for e in audit]


def test_a_model_cannot_reach_a_tool_outside_its_agent():
    model = ScriptedModel([
        openai_reply(openai_call("c1", "StartProduction")),
        openai_reply(content="ok"),
    ])
    r = start(client_for("openai", model), "start it")
    step = r["steps"][0]
    assert step["status"] == "refused" and step["output"] == "ERROR: tool not available to this agent"


def test_anthropic_loop_batches_tool_results_in_one_user_turn():
    model = ScriptedModel([
        anthropic_reply(
            {"type": "text", "text": "Looking up."},
            {"type": "tool_use", "id": "t1", "name": "SearchPatients", "input": {"query": "maria"}},
            {"type": "tool_use", "id": "t2", "name": "FetchPatientSummary", "input": {"patientId": MARIA}},
        ),
        anthropic_reply({"type": "text", "text": "Done."}, stop="end_turn"),
    ])
    r = start(client_for("anthropic", model), "Assess Maria")
    assert r["status"] == "succeeded" and r["output"] == "Done."
    req = model.requests[1]
    assert req["url"].endswith("/v1/messages")
    assert req["headers"]["x-api-key"] == "test-key"
    assert req["headers"]["anthropic-version"] == "2023-06-01"
    assert "Community Health Worker" in req["body"]["system"]
    last = req["body"]["messages"][-1]
    assert last["role"] == "user"
    assert [b["tool_use_id"] for b in last["content"]] == ["t1", "t2"]
    assert "input_schema" in req["body"]["tools"][0]


def test_provider_errors_fail_the_run_with_a_useful_message():
    model = ScriptedModel([])
    model.handle = lambda request: httpx.Response(500, text="")
    r = start(client_for("openai", model), "x")
    assert r["status"] == "failed"
    assert "check base_url, model name and api key" in r["error"]


@pytest.mark.parametrize("engine", ["openai", "anthropic"])
def test_runaway_loops_stop_at_max_turns(engine):
    if engine == "openai":
        reply = openai_reply(openai_call("c", "GetProductionStatus"))
    else:
        reply = anthropic_reply({"type": "tool_use", "id": "t", "name": "GetProductionStatus", "input": {}})
    model = ScriptedModel([reply] * 20)
    r = start(client_for(engine, model), "loop")
    assert r["status"] == "failed" and "max_turns=12" in r["error"]

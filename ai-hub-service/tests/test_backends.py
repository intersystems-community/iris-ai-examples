"""The MCP and IRIS backends, against fakes that fail the way the real ones do."""

from __future__ import annotations

import json

import httpx
import pytest
from careconnect_evals.tools_local import PATIENTS, TOOL_SCHEMAS, LocalToolClient
from fakes import FakeLegacyIRIS, FakeMCPServer

from aihub_service.backends import BackendError
from aihub_service.backends.iris_backend import IRISBackend
from aihub_service.backends.mcp_backend import MCPBackend
from aihub_service.catalog import ToolSpec


def spec(name, **binding):
    return ToolSpec(name=name, backend="b", remote_name=name, binding=binding)


STOCK = {"url": "http://hub/mcp/careconnect", "tool_prefix": "mcp_careconnect_"}


# -- MCP ---------------------------------------------------------------------


@pytest.mark.parametrize("sse", [False, True], ids=["json", "event-stream"])
def test_mcp_handshake_list_and_call(sse):
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS, sse=sse)
    b = MCPBackend("hub", {**STOCK, "username": "_SYSTEM", "password": "SYS"},
                   transport=server.transport())
    assert "AssessSDoHRisk" in b.list_tools()
    out = b.call(spec("SearchPatients"), {"query": "james"})
    assert "patientId: james-okafor-002" in out
    methods = [r["msg"]["method"] for r in server.requests]
    assert methods[:3] == ["initialize", "notifications/initialized", "tools/list"]
    # Session id echoed back, basic auth sent, both content types accepted.
    later = server.requests[-1]["headers"]
    assert later["mcp-session-id"] == "sess-1"
    assert later["authorization"].startswith("Basic ")
    assert "text/event-stream" in later["accept"]


def test_mcp_describe_reads_the_servers_schema():
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", STOCK, transport=server.transport())
    d = b.describe("FetchPatientSummary")
    assert d["parameters"]["required"] == ["patientId"]
    assert b.describe("NotATool") is None


def test_mcp_sends_the_published_name_and_lists_the_bare_one():
    # iris-mcp-server 2.0.0 on build 139 publishes /mcp/careconnect's tools as
    # mcp_careconnect_<Tool>; measured against a stock container 2026-09-23.
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", STOCK, transport=server.transport())
    assert set(b.list_tools()) == {s["name"] for s in TOOL_SCHEMAS}
    assert "patientId: james-okafor-002" in b.call(spec("SearchPatients"), {"query": "james"})
    assert server.requests[-1]["msg"]["params"]["name"] == "mcp_careconnect_SearchPatients"


def test_mcp_peels_the_string_encoding_off_a_string_tools_answer():
    # Stock iris-mcp-server returns a %String result as '"line1\\nline2"'.
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", STOCK, transport=server.transport())
    out = b.call(spec("FetchPatientSummary"), {"patientId": "maria-gonzalez-001"})
    assert out == LocalToolClient().FetchPatientSummary("maria-gonzalez-001")
    assert b.call(spec("FetchPatientSummary"), {"patientId": ""}) == "ERROR: patientId is required"


def test_mcp_leaves_an_answer_that_is_not_a_json_string_alone():
    # An object-returning tool is not wrapped; nor is bare text.
    for text in ('{"a": 1}', "plain text", '"unterminated'):
        b = MCPBackend("hub", STOCK, transport=httpx.MockTransport(
            lambda r, t=text: _raw_text_reply(r, t)))
        assert b.call(spec("Echo"), {}) == text


def _raw_text_reply(request, text):
    msg = json.loads(request.content)
    if msg.get("method") == "initialize":
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {}})
    if "id" not in msg:
        return httpx.Response(202)
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"],
                                     "result": {"content": [{"type": "text", "text": text}]}})


def test_mcp_without_the_prefix_cannot_reach_a_stock_server():
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", {"url": "http://hub/mcp/careconnect"}, transport=server.transport())
    assert b.describe("SearchPatients") is None
    assert "no registered service found" in b.call(spec("SearchPatients"), {})


def test_mcp_tool_error_is_text_not_an_exception():
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", STOCK, transport=server.transport())
    assert b.call(spec("Missing"), {}).startswith("ERROR")


def test_mcp_down_is_a_backend_error_and_unready():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    b = MCPBackend("hub", {"url": "http://hub/mcp"}, transport=httpx.MockTransport(refuse))
    with pytest.raises(BackendError, match="ConnectError"):
        b.call(spec("SearchPatients"), {})
    assert b.health()["ok"] is False
    assert b.describe("SearchPatients") is None


def test_mcp_session_loss_reinitializes_once():
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", STOCK, transport=server.transport())
    b.call(spec("SearchPatients"), {})
    server.session_id = "sess-2"  # iris-mcp-server restarted
    assert "Available patients" in b.call(spec("SearchPatients"), {})
    assert [r["msg"]["method"] for r in server.requests].count("initialize") == 2


# -- IRIS (Native API) -------------------------------------------------------


def test_iris_sql_binding_with_params_and_text_format():
    legacy = FakeLegacyIRIS(PATIENTS)
    b = IRISBackend("legacy", {"host": "h"}, connect=legacy.connect)
    out = b.call(spec("X", sql="SELECT Name, Demographics FROM CareConnect.Patient WHERE PatientId = ?",
                      params=["${args.id}"]), {"id": "sarah-kim-003"})
    assert out == "Name: Sarah Kim\nDemographics: 29F"


def test_iris_sql_json_format_and_empty_message():
    legacy = FakeLegacyIRIS(PATIENTS)
    b = IRISBackend("legacy", {"host": "h"}, connect=legacy.connect)
    tool = spec("X", sql="SELECT PatientId FROM CareConnect.Patient WHERE Name = ?",
                params=["${args.n}"], format="json", empty="none called ${args.n}")
    assert b.call(tool, {"n": "Maria Gonzalez"}) == '[{"PatientId": "maria-gonzalez-001"}]'
    assert b.call(tool, {"n": "Zed"}) == "none called Zed"


def test_iris_classmethod_binding_renders_json_args():
    legacy = FakeLegacyIRIS(PATIENTS)
    b = IRISBackend("legacy", {"host": "h"}, connect=legacy.connect)
    tool = spec("T", classmethod="AIHub.Legacy.Interop.Dispatch",
                args=["CareConnect.Service.SDoHFollowUpBS", "CareConnect.Message.FollowUpRequest",
                      {"json": {"PatientId": "${args.p}"}}])
    out = b.call(tool, {"p": "maria-gonzalez-001"})
    assert '"status": "ok"' in out
    assert legacy.calls[0][2][2] == '{"PatientId":"maria-gonzalez-001"}'


def test_iris_reconnects_once_after_a_dropped_connection():
    legacy = FakeLegacyIRIS(PATIENTS)
    b = IRISBackend("legacy", {"host": "h"}, connect=legacy.connect)
    tool = spec("X", sql="SELECT COUNT(*) AS n FROM CareConnect.Patient")
    assert b.call(tool, {}) == "n: 3"
    b._conn = _Broken()  # the pod restarted under us
    assert b.call(tool, {}) == "n: 3"
    assert legacy.connects == 2


def test_iris_that_stays_down_is_a_backend_error():
    def down(spec):
        raise ConnectionRefusedError("superserver not listening")

    b = IRISBackend("legacy", {"host": "h"}, connect=down)
    with pytest.raises(BackendError, match="superserver not listening"):
        b.call(spec("X", sql="SELECT 1"), {})
    assert b.health()["ok"] is False


class _Broken:
    def cursor(self):
        raise OSError("connection reset")

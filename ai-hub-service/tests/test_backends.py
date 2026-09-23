"""The MCP and IRIS backends, against fakes that fail the way the real ones do."""

from __future__ import annotations

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


# -- MCP ---------------------------------------------------------------------


@pytest.mark.parametrize("sse", [False, True], ids=["json", "event-stream"])
def test_mcp_handshake_list_and_call(sse):
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS, sse=sse)
    b = MCPBackend("hub", {"url": "http://hub/mcp/careconnect", "username": "_SYSTEM",
                           "password": "SYS"}, transport=server.transport())
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
    b = MCPBackend("hub", {"url": "http://hub/mcp"}, transport=server.transport())
    d = b.describe("FetchPatientSummary")
    assert d["parameters"]["required"] == ["patientId"]
    assert b.describe("NotATool") is None


def test_mcp_tool_error_is_text_not_an_exception():
    server = FakeMCPServer(LocalToolClient(), TOOL_SCHEMAS)
    b = MCPBackend("hub", {"url": "http://hub/mcp"}, transport=server.transport())
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
    b = MCPBackend("hub", {"url": "http://hub/mcp"}, transport=server.transport())
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

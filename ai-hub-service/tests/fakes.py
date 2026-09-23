"""Stand-ins for the two kinds of IRIS the service talks to, for tests with no Docker.

FakeMCPServer
    An MCP streamable-HTTP endpoint (the shape iris-mcp-server serves) in front
    of any object whose methods are tools. Like the stock server it publishes
    each tool under its web application's prefix, ``mcp_careconnect_<Tool>``,
    answers a bare name with isError, and returns a %String tool's answer as a
    JSON string literal, quotes and escapes included (every SDoHToolSet tool
    returns %String). In CareConnect tests that object is
    the eval suite's LocalToolClient — the faithful port of SDoHToolSet — so a
    tool answered "over MCP" returns what the ObjectScript returns.

FakeLegacyIRIS
    A pre-AI-Hub IRIS as the Native API sees it. SQL runs for real, on SQLite,
    against tables whose columns are read from the shipped .cls files — so a
    column the sidecar config names but the class lacks fails the test, as it
    would fail on IRIS. classMethodValue dispatches to a Python simulation of
    AIHub.Legacy.Interop; that part is a model of the ObjectScript, not the
    ObjectScript, and says so.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
PATIENT_CLS = REPO / "careconnect-sdoh" / "src" / "CareConnect" / "Patient.cls"


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------


class FakeMCPServer:
    def __init__(self, target, schemas, sse: bool = False, session_id: str = "sess-1",
                 prefix: str = "mcp_careconnect_"):
        self.target = target
        self.prefix = prefix
        self.schemas = {s["name"]: s for s in schemas}
        self.sse = sse
        self.session_id = session_id
        self.requests: list[dict] = []
        self.initialized = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        msg = json.loads(request.content)
        self.requests.append({"msg": msg, "headers": dict(request.headers)})
        method = msg.get("method")
        if method == "initialize":
            self.initialized = True
            return self._reply(msg, {
                "protocolVersion": msg["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-iris-mcp", "version": "0"},
            }, extra_headers={"Mcp-Session-Id": self.session_id})
        if request.headers.get("mcp-session-id") != self.session_id:
            return httpx.Response(400, text="missing or wrong Mcp-Session-Id")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            tools = [
                {"name": self.prefix + n, "description": s["description"], "inputSchema": s["parameters"]}
                for n, s in self.schemas.items()
            ]
            return self._reply(msg, {"tools": tools})
        if method == "tools/call":
            published = msg["params"]["name"]
            name = published[len(self.prefix):] if published.startswith(self.prefix) else None
            fn = getattr(self.target, name, None) if name else None
            if fn is None or name not in self.schemas:
                text = f"Service unavailable: no registered service found for tool '{published}'"
                return self._reply(msg, {"content": [{"type": "text", "text": text}], "isError": True})
            text = json.dumps(str(fn(**msg["params"].get("arguments", {}))))
            return self._reply(msg, {"content": [{"type": "text", "text": text}], "isError": False})
        return self._reply(msg, None, error={"code": -32601, "message": f"no method {method}"})

    def _reply(self, msg, result, error=None, extra_headers=None) -> httpx.Response:
        body = {"jsonrpc": "2.0", "id": msg["id"]}
        if error:
            body["error"] = error
        else:
            body["result"] = result
        headers = dict(extra_headers or {})
        if self.sse:
            headers["content-type"] = "text/event-stream"
            text = f"event: message\ndata: {json.dumps(body)}\n\n"
            return httpx.Response(200, text=text, headers=headers)
        return httpx.Response(200, json=body, headers=headers)


# --------------------------------------------------------------------------
# Legacy IRIS
# --------------------------------------------------------------------------


def persistent_properties(cls_path: Path) -> list[str]:
    return re.findall(r"^Property\s+(\w+)", cls_path.read_text(encoding="utf-8"), re.M)


class _Cursor:
    def __init__(self, db: sqlite3.Connection):
        self._cur = db.cursor()
        self.description = None

    def execute(self, sql: str, params=()):
        params = list(params)
        # IRIS: SELECT TOP n ...   SQLite: SELECT ... LIMIT n
        m = re.match(r"(?is)^\s*SELECT\s+TOP\s+(\?|\d+)\s+(.*)$", sql)
        if m:
            limit = params.pop(0) if m.group(1) == "?" else m.group(1)
            sql, params = f"SELECT {m.group(2)} LIMIT ?", params + [int(limit)]
        self._cur.execute(sql, params)
        self.description = self._cur.description
        return self

    def fetchall(self):
        return self._cur.fetchall()

    def close(self):
        self._cur.close()


class FakeLegacyIRIS:
    def __init__(self, patients: dict, production_running: bool = True):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("ATTACH DATABASE ':memory:' AS CareConnect")
        self.db.execute("ATTACH DATABASE ':memory:' AS Ens")
        cols = persistent_properties(PATIENT_CLS)
        self.db.execute(f"CREATE TABLE CareConnect.Patient ({', '.join(cols)})")
        for pid, p in patients.items():
            row = {"PatientId": pid, **p}
            self.db.execute(
                f"INSERT INTO CareConnect.Patient ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [row.get(c) for c in cols],
            )
        self.db.execute(
            "CREATE TABLE Ens.MessageHeader (ID INTEGER PRIMARY KEY, SourceConfigName, "
            "TargetConfigName, MessageBodyClassName, TimeCreated, Status)"
        )
        self.production = "CareConnect.Production"
        self.running = production_running
        self.allow = {"CareConnect.Service.SDoHFollowUpBS": "CareConnect.Message.FollowUpRequest"}
        self.calls: list[tuple] = []
        self.connects = 0

    # -- what iris.connect / iris.createIRIS hand back --

    def connect(self, spec):
        self.connects += 1
        return self, self

    def cursor(self):
        return _Cursor(self.db)

    def classMethodValue(self, cls, method, *args):
        self.calls.append((cls, method, args))
        if cls != "AIHub.Legacy.Interop":
            raise RuntimeError(f"<CLASS DOES NOT EXIST> {cls}")
        return getattr(self, f"_interop_{method}")(*args)

    # -- a model of AIHub.Legacy.Interop, for the service-side tests --

    def _interop_Dispatch(self, service, request_class, props_json):
        if self.allow.get(service) != request_class:
            return json.dumps({"status": "forbidden", "error": f"{service} not allowed"})
        if not self.running:
            return json.dumps({"status": "not_running", "production": self.production})
        props = json.loads(props_json or "{}")
        job = str(uuid.uuid4()).upper()
        now = datetime(2026, 9, 23, 12, 0, 0).isoformat(sep=" ")
        # BS -> BP (sync), BP -> BO (async, response required), BO -> BP, BP -> BS:
        # the four headers SDoHFollowUpBP's flow leaves in Ens.MessageHeader.
        for src, tgt, body in [
            ("CareConnect.Service.SDoHFollowUpBS", "CareConnect.Process.SDoHFollowUpBP", "CareConnect.Message.FollowUpRequest"),
            ("CareConnect.Process.SDoHFollowUpBP", "CareConnect.Operation.SDoHFollowUpBO", "CareConnect.Message.FollowUpRequest"),
            ("CareConnect.Operation.SDoHFollowUpBO", "CareConnect.Process.SDoHFollowUpBP", "CareConnect.Message.FollowUpResponse"),
            ("CareConnect.Process.SDoHFollowUpBP", "CareConnect.Service.SDoHFollowUpBS", "CareConnect.Message.FollowUpResponse"),
        ]:
            self.db.execute(
                "INSERT INTO Ens.MessageHeader (SourceConfigName, TargetConfigName, "
                "MessageBodyClassName, TimeCreated, Status) VALUES (?,?,?,?,?)",
                [src, tgt, body, now, 9],
            )
        self.last_request = props
        return json.dumps({"status": "ok", "service": service,
                           "response": {"Status": "accepted", "JobId": job, "Error": ""}})

    def _interop_ProductionStatus(self):
        state = "Running" if self.running else "Stopped"
        return f"Production: {self.production}\nStatus: {state}\n"

    def _interop_StartProduction(self, name):
        if self.running:
            return f"Production already running: {self.production}"
        self.running, self.production = True, name
        return f"Production started: {name} (Running)"

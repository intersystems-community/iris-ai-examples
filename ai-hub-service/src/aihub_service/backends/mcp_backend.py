"""Tools served by an AI Hub IRIS through its MCP endpoint.

iris-mcp-server fronts ``%AI.MCP.Service`` (in careconnect-sdoh: the
``/mcp/careconnect`` web application, 18 tools from SDoHToolSet). This client
speaks the MCP streamable-HTTP transport: JSON-RPC 2.0 over POST, a response
that is either ``application/json`` or a ``text/event-stream`` carrying the
same JSON-RPC message, and an ``Mcp-Session-Id`` header the server may issue on
``initialize`` and expects back on every later request.

iris-mcp-server publishes each tool under its web application's prefix —
``mcp_careconnect_AssessSDoHRisk`` for ``/mcp/careconnect`` — and answers a
bare name with "no registered service found". ``tool_prefix`` names that
prefix: the catalog keeps the bare names, and the prefix is added on the wire.
It also returns a %String tool's answer as a JSON string literal — quotes,
``\\n`` escapes and all — so a text answer is decoded once before anyone reads
it, including the playbook looking for ``ERROR``.

It is a deliberately small client — tools/list and tools/call are all the
service needs — so it carries no MCP SDK dependency.
"""

from __future__ import annotations

import itertools
import json
import threading

import httpx

from . import BackendError

PROTOCOL_VERSION = "2025-03-26"


class MCPBackend:
    kind = "mcp"

    def __init__(self, name: str, spec: dict, transport: httpx.BaseTransport | None = None):
        self.name = name
        self.spec = spec
        self.url = spec["url"]
        self.prefix = spec.get("tool_prefix", "")
        auth = None
        if spec.get("username"):
            auth = (spec["username"], spec.get("password", ""))
        headers = {"Accept": "application/json, text/event-stream"}
        if spec.get("token"):
            headers["Authorization"] = f"Bearer {spec['token']}"
        self._http = httpx.Client(
            timeout=float(spec.get("timeout", 120)),
            auth=auth,
            headers=headers,
            transport=transport,
        )
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._session: str | None = None
        self._initialized = False
        self._tools: dict[str, dict] | None = None

    # -- JSON-RPC ----------------------------------------------------------

    def _post(self, payload: dict) -> dict | None:
        headers = {"Mcp-Session-Id": self._session} if self._session else {}
        try:
            r = self._http.post(self.url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise BackendError(f"{self.name}: {type(exc).__name__}: {exc}") from exc
        if r.headers.get("mcp-session-id"):
            self._session = r.headers["mcp-session-id"]
        if r.status_code == 202 or "id" not in payload:
            return None  # notification accepted
        if r.status_code >= 400:
            raise BackendError(f"{self.name}: HTTP {r.status_code} from {self.url}: {r.text[:200]}")
        message = _parse_response(r, payload["id"])
        if "error" in message:
            err = message["error"]
            raise BackendError(f"{self.name}: MCP error {err.get('code')}: {err.get('message')}")
        return message.get("result", {})

    def _request(self, method: str, params: dict | None = None) -> dict:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            payload["params"] = params
        return self._post(payload) or {}

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aihub-service", "version": "0.1.0"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True

    # -- backend protocol --------------------------------------------------

    def list_tools(self) -> dict[str, dict]:
        with self._lock:
            if self._tools is None:
                self._ensure_initialized()
                tools, cursor = {}, None
                while True:
                    result = self._request("tools/list", {"cursor": cursor} if cursor else {})
                    for t in result.get("tools", []):
                        if t["name"].startswith(self.prefix):
                            tools[t["name"][len(self.prefix):]] = t
                    cursor = result.get("nextCursor")
                    if not cursor:
                        break
                self._tools = tools
            return self._tools

    def call(self, tool, args: dict) -> str:
        with self._lock:
            self._ensure_initialized()
            params = {"name": self.prefix + tool.remote_name, "arguments": args}
            try:
                result = self._request("tools/call", params)
            except BackendError:
                # A restarted iris-mcp-server forgets our session; start a new one once.
                self._initialized, self._session = False, None
                self._ensure_initialized()
                result = self._request("tools/call", params)
        text = _unwrap("\n".join(
            c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"
        ))
        if result.get("isError"):
            return text if text.startswith("ERROR") else f"ERROR: {text}"
        return text

    def describe(self, remote_name: str) -> dict | None:
        try:
            t = self.list_tools().get(remote_name)
        except BackendError:
            return None
        if not t:
            return None
        return {
            "description": t.get("description", ""),
            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
        }

    def health(self, expected: list[str] = ()) -> dict:
        """Ready only if the server publishes every tool the catalog binds here."""
        try:
            self._tools = None
            listed = self.list_tools()
        except BackendError as exc:
            return {"ok": False, "detail": str(exc)}
        missing = sorted(set(expected) - set(listed))
        if missing:
            return {"ok": False, "detail": f"{self.url} publishes {len(listed)} tools"
                    f"{f' under {self.prefix!r}' if self.prefix else ''} but not: {', '.join(missing)}"}
        return {"ok": True, "detail": f"{self.url} ({len(listed)} tools)"}


def _unwrap(text: str) -> str:
    """A JSON string literal becomes the string; anything else is left as it came."""
    try:
        decoded = json.loads(text)
    except ValueError:
        return text
    return decoded if isinstance(decoded, str) else text


def _parse_response(r: httpx.Response, want_id) -> dict:
    ctype = r.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for block in r.text.split("\n\n"):
            data = "\n".join(
                line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
            )
            if not data:
                continue
            msg = json.loads(data)
            if msg.get("id") == want_id:
                return msg
        raise BackendError(f"no JSON-RPC response with id {want_id} in the event stream")
    try:
        return r.json()
    except ValueError as exc:
        raise BackendError(f"non-JSON MCP response: {r.text[:200]}") from exc

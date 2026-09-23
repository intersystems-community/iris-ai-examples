"""Tool backends: where a tool's code actually runs.

Every backend answers the same three questions, so the catalog, the agent
runtime and the governance layer never learn which IRIS a tool lives on:

    call(tool, args) -> str       run it; tools return text, as %AI.ToolSet does
    describe(name)  -> dict|None  its schema, if the backend can say
    health()        -> dict       {"ok": bool, "detail": str}

Three kinds ship:

    mcp     an AI Hub IRIS, through iris-mcp-server in front of %AI.MCP.Service
    iris    any IRIS version, through the Native API — SQL or a classmethod.
            This is what lets a pre-AI-Hub instance serve tools unmodified.
    python  an in-process object or function; the offline mode and tests
"""

from __future__ import annotations

from typing import Protocol


class BackendError(RuntimeError):
    """A backend could not run the call at all (as opposed to a tool that ran
    and reported an error in its text, which is ordinary tool output)."""


class Backend(Protocol):
    name: str
    kind: str

    def call(self, tool, args: dict) -> str: ...

    def describe(self, remote_name: str) -> dict | None: ...

    def health(self) -> dict: ...


def build_backend(name: str, spec: dict, **overrides) -> Backend:
    kind = spec.get("kind")
    if kind == "python":
        from .python_backend import PythonBackend

        return PythonBackend(name, spec)
    if kind == "iris":
        from .iris_backend import IRISBackend

        return IRISBackend(name, spec, connect=overrides.get("iris_connect"))
    if kind == "mcp":
        from .mcp_backend import MCPBackend

        return MCPBackend(name, spec, transport=overrides.get("http_transport"))
    raise ValueError(f"backend {name}: unknown kind {kind!r} (want mcp, iris or python)")

"""The tool catalog: one list of tools, each bound to the backend that runs it.

The catalog is the mesh. In the sidecar topology CareConnect's patient lookup
binds to the legacy IRIS over SQL while the SDoH scorer binds to the AI Hub
companion over MCP, and nothing above this module can tell. A caller sees one
catalog; an agent sees one tool list; the audit trail records which backend
answered each call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .backends import Backend, BackendError, build_backend

EMPTY_SCHEMA = {"type": "object", "properties": {}}


@dataclass
class ToolSpec:
    name: str
    backend: str
    remote_name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(EMPTY_SCHEMA))
    effect: str = "read"  # read | write — write tools pass through the approval policy
    binding: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "effect": self.effect,
            "backend": self.backend,
        }


@dataclass
class ToolResult:
    tool: str
    backend: str
    output: str
    ok: bool
    elapsed_ms: int


class Catalog:
    def __init__(self, cfg, **backend_overrides):
        self.backends: dict[str, Backend] = {
            name: build_backend(name, spec, **backend_overrides)
            for name, spec in cfg.backends.items()
        }
        self.tools: dict[str, ToolSpec] = {}
        for t in cfg.tools:
            self.tools[t["name"]] = ToolSpec(
                name=t["name"],
                backend=t["backend"],
                remote_name=t.get("remote_name", t["name"]),
                description=t.get("description", ""),
                parameters=t.get("parameters") or {},
                effect=t.get("effect", "read"),
                binding=t.get("binding", {}),
            )
        self._described = False

    def _describe_all(self) -> None:
        """Fill descriptions and schemas the config left out from the backend.

        Lazy, because an MCP backend answers only once its IRIS is up, and the
        service must start (and report unready) before that.
        """
        if self._described:
            return
        complete = True
        for spec in self.tools.values():
            if spec.description and spec.parameters:
                continue
            found = self.backends[spec.backend].describe(spec.remote_name)
            if found is None:
                complete = complete and bool(spec.description)
                continue
            spec.description = spec.description or found.get("description", "")
            spec.parameters = spec.parameters or found.get("parameters") or dict(EMPTY_SCHEMA)
        for spec in self.tools.values():
            spec.parameters = spec.parameters or dict(EMPTY_SCHEMA)
        self._described = complete

    def list(self, names: list[str] | None = None) -> list[ToolSpec]:
        self._describe_all()
        wanted = names if names is not None else list(self.tools)
        return [self.tools[n] for n in wanted if n in self.tools]

    def get(self, name: str) -> ToolSpec | None:
        self._describe_all()
        return self.tools.get(name)

    def invoke(self, name: str, args: dict) -> ToolResult:
        spec = self.tools[name]
        started = time.monotonic()
        try:
            out = self.backends[spec.backend].call(spec, args or {})
            ok = not out.startswith("ERROR")
        except BackendError as exc:
            out, ok = f"ERROR: backend {spec.backend} unavailable: {exc}", False
        return ToolResult(
            tool=name,
            backend=spec.backend,
            output=out,
            ok=ok,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    def health(self) -> dict:
        out = {}
        for name, b in self.backends.items():
            bound = [t.remote_name for t in self.tools.values() if t.backend == name]
            out[name] = b.health(expected=bound) if b.kind == "mcp" else b.health()
        return out

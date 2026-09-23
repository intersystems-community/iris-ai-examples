"""In-process tools: an object whose methods are tools, or bare functions.

The CareConnect offline mode binds this to ``careconnect_evals.tools_local``,
the faithful Python port of SDoHToolSet that the eval suite already keeps in
parity with the ObjectScript. The service therefore runs the same rule the
IRIS build runs, with no Docker and no IRIS.
"""

from __future__ import annotations

import importlib
import threading
from typing import Any


def resolve(ref: str) -> Any:
    """``package.module:attr`` -> the attribute."""
    module, _, attr = ref.partition(":")
    if not attr:
        raise ValueError(f"expected module:attribute, got {ref!r}")
    obj: Any = importlib.import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


class PythonBackend:
    kind = "python"

    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec
        self._lock = threading.Lock()
        self._target = None
        self._schemas: dict[str, dict] = {}
        if spec.get("object"):
            factory = resolve(spec["object"])
            kwargs = spec.get("object_kwargs", {})
            self._target = factory(**kwargs) if callable(factory) else factory
        if spec.get("schemas"):
            for s in resolve(spec["schemas"]):
                self._schemas[s["name"]] = {
                    "description": s.get("description", ""),
                    "parameters": s.get("parameters", {"type": "object", "properties": {}}),
                }

    def _callable(self, tool):
        binding = tool.binding or {}
        if binding.get("function"):
            return resolve(binding["function"])
        if self._target is None:
            raise ValueError(f"tool {tool.name}: backend {self.name} has no object and no function")
        fn = getattr(self._target, tool.remote_name, None)
        if fn is None:
            raise ValueError(f"tool {tool.name}: {type(self._target).__name__} has no {tool.remote_name}")
        return fn

    def call(self, tool, args: dict) -> str:
        fn = self._callable(tool)
        # One shared object stands in for one shared IRIS instance: the offline
        # production's running state and message log are global, as they are live.
        with self._lock:
            try:
                return str(fn(**args))
            except TypeError as exc:
                return f"ERROR: bad arguments for {tool.name}: {exc}"

    def describe(self, remote_name: str) -> dict | None:
        return self._schemas.get(remote_name)

    def health(self) -> dict:
        return {"ok": True, "detail": f"in-process ({self.spec.get('object') or 'functions'})"}

"""Tools served by any IRIS instance over the Native API — no %AI required.

This backend is what makes the sidecar topology work. A pre-AI-Hub IRIS
(2023.x, 2024.x, 2025.x) cannot compile a %AI.ToolSet, but it can answer SQL
and run a classmethod over the superserver, and that is all a tool needs. The
tool's schema and governance live in the service config; the IRIS side is
untouched application code.

Two binding shapes:

    binding:
      sql: SELECT Name, Notes FROM CareConnect.Patient WHERE PatientId = ?
      params: ["${args.patientId}"]
      format: text | json | python:module:function
      empty: "Patient not found: ${args.patientId}"

    binding:
      classmethod: AIHub.Legacy.Interop.Dispatch
      args:
        - CareConnect.Service.SDoHFollowUpBS
        - json: {PatientId: "${args.patientId}"}

A binding may also carry ``cases:`` — a list of the above with a ``when:``
condition, first match wins — for a tool whose query depends on which
arguments were given. A case may answer with a constant ``result:`` instead,
for argument checks the original tool made before touching the database.

``format: python:module:function`` hands a SQL result's rows — or a
classmethod's return string — to a deployment-supplied formatter along with
the call's arguments. That is how a legacy route reproduces an existing tool's
output exactly.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

from ..templating import render, truthy
from . import BackendError
from .python_backend import resolve


def _default_connect(spec: dict):
    try:
        import iris  # intersystems-irispython
    except ImportError as exc:  # pragma: no cover - depends on the image
        raise BackendError(
            "the iris backend needs intersystems-irispython (pip install intersystems-irispython)"
        ) from exc
    conn = iris.connect(
        hostname=spec["host"],
        port=int(spec.get("port", 1972)),
        namespace=spec.get("namespace", "USER"),
        username=spec.get("username", "_SYSTEM"),
        password=spec.get("password", "SYS"),
        timeout=int(spec.get("timeout_ms", 10000)),
    )
    return conn, iris.createIRIS(conn)


class IRISBackend:
    kind = "iris"

    def __init__(self, name: str, spec: dict, connect: Callable | None = None):
        self.name = name
        self.spec = spec
        self._connect = connect or _default_connect
        self._lock = threading.Lock()
        self._conn = None
        self._native = None

    # -- connection --------------------------------------------------------

    def _ensure(self):
        if self._conn is None:
            self._conn, self._native = self._connect(self.spec)
        return self._conn, self._native

    def _with_retry(self, fn):
        """One reconnect on failure: a superserver connection dropped by a pod
        restart should cost one retry, not an outage."""
        with self._lock:
            try:
                return fn(*self._ensure())
            except BackendError:
                raise
            except Exception:
                self._conn = self._native = None
                try:
                    return fn(*self._ensure())
                except Exception as exc:
                    raise BackendError(f"{self.name}: {type(exc).__name__}: {exc}") from exc

    # -- calls -------------------------------------------------------------

    def call(self, tool, args: dict) -> str:
        binding = tool.binding or {}
        scope = {"args": args, "tool": {"name": tool.name}}
        if "cases" in binding:
            chosen = next((c for c in binding["cases"] if truthy(c.get("when"), scope)), None)
            if chosen is None:
                return f"ERROR: no case of {tool.name} matches the arguments given"
            binding = {k: v for k, v in binding.items() if k != "cases"}
            binding.update(chosen)
        if "result" in binding:
            # A case that answers without a round trip — argument validation
            # the ObjectScript tool would have done before touching IRIS.
            return str(render(binding["result"], scope))
        if binding.get("sql"):
            return self._sql(tool, binding, scope)
        if binding.get("classmethod"):
            return self._classmethod(binding, scope)
        raise BackendError(f"tool {tool.name}: iris binding needs sql or classmethod")

    def _sql(self, tool, binding: dict, scope: dict) -> str:
        params = [render(p, scope) for p in binding.get("params", [])]

        def run(conn, _native):
            cur = conn.cursor()
            try:
                cur.execute(binding["sql"], params)
                cols = [d[0] for d in (cur.description or [])]
                return cols, [list(r) for r in cur.fetchall()]
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

        cols, rows = self._with_retry(run)
        records = [dict(zip(cols, r)) for r in rows]
        if not records and binding.get("empty"):
            return str(render(binding["empty"], scope))
        return format_rows(records, binding.get("format", "text"), scope)

    def _classmethod(self, binding: dict, scope: dict) -> str:
        cls, _, method = binding["classmethod"].rpartition(".")
        if not cls:
            raise BackendError(f"classmethod must be Class.Name.Method, got {binding['classmethod']!r}")
        values = [_render_arg(a, scope) for a in binding.get("args", [])]
        result = self._with_retry(lambda _conn, native: native.classMethodValue(cls, method, *values))
        text = "" if result is None else str(result)
        fmt = binding.get("format", "text")
        if fmt.startswith("python:"):
            return str(resolve(fmt[len("python:"):])(text, scope.get("args", {})))
        return text

    def describe(self, remote_name: str) -> dict | None:
        return None  # schemas for iris tools are declared in the config

    def health(self) -> dict:
        try:
            self._with_retry(lambda conn, _n: conn.cursor().execute("SELECT 1"))
            return {"ok": True, "detail": f"{self.spec.get('host')}:{self.spec.get('port', 1972)}"}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}


def _render_arg(arg: Any, scope: dict) -> Any:
    if isinstance(arg, dict) and set(arg) == {"json"}:
        return json.dumps(render(arg["json"], scope), separators=(",", ":"))
    value = render(arg, scope)
    return "" if value is None else value


def format_rows(records: list[dict], fmt: str, scope: dict) -> str:
    if fmt == "json":
        return json.dumps(records, default=str)
    if fmt.startswith("python:"):
        return str(resolve(fmt[len("python:"):])(records, scope.get("args", {})))
    if fmt != "text":
        raise BackendError(f"unknown format {fmt!r} (want text, json or python:module:function)")
    if not records:
        return "No rows."
    blocks = ["\n".join(f"{k}: {'' if v is None else v}" for k, v in r.items()) for r in records]
    return "\n\n".join(blocks)

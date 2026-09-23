"""Runs: one agent execution, from request to answer, with every step recorded.

A run is the unit a caller holds on to. It moves through

    running -> awaiting_approval -> running -> succeeded
                                            -> failed
            -> cancelled

and carries its own audit trail: every tool call with its arguments, the
backend that answered, the output, the time it took, and — for a gated call —
who approved or rejected it and why. That record is what a clinical-safety
review asks for, and it exists whichever engine chose the calls.

The store is an interface. The in-memory store here is for a single replica;
a multi-replica deployment swaps in a durable one (the design names IRIS
globals on the companion instance) without touching the lifecycle.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .engines import EngineError, Final, PlannedCall

TERMINAL = {"succeeded", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Run:
    agent: str
    input: str
    context: dict
    principal: str
    id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:16]}")
    status: str = "running"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    steps: list = field(default_factory=list)
    pending: list = field(default_factory=list)  # PlannedCall dicts not yet executed
    awaiting: dict | None = None
    approved: dict = field(default_factory=dict)  # call id -> approver
    output: str = ""
    error: str = ""
    events: list = field(default_factory=list)
    callback_url: str | None = None
    engine_state: dict = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def event(self, kind: str, detail: dict | None = None) -> None:
        self.events.append({"at": _now(), "type": kind, **(detail or {})})
        self.updated_at = _now()

    def public(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "status": self.status,
            "input": self.input,
            "context": self.context,
            "principal": self.principal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output": self.output,
            "error": self.error,
            "awaiting_approval": self.awaiting,
            "steps": self.steps,
            "events": self.events,
        }


class InMemoryRunStore:
    def __init__(self, limit: int = 1000):
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self._limit = limit

    def put(self, run: Run) -> None:
        with self._lock:
            self._runs[run.id] = run
            if len(self._runs) > self._limit:
                # Oldest terminal runs go first; a run awaiting a human never ages out.
                for rid in [r.id for r in self._runs.values() if r.status in TERMINAL]:
                    if len(self._runs) <= self._limit:
                        break
                    del self._runs[rid]

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self, status: str | None = None, principal: str | None = None) -> list[Run]:
        runs = list(self._runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        if principal:
            runs = [r for r in runs if r.principal == principal]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)


class Runner:
    """Drives runs forward: asks the engine, applies policy, executes, records."""

    def __init__(self, catalog, policy, engines: dict, agents: dict, audit, on_settle=None):
        self.catalog = catalog
        self.policy = policy
        self.engines = engines
        self.agents = agents
        self.audit = audit
        self.on_settle = on_settle  # called when a run stops moving (callbacks)

    def start(self, run: Run) -> Run:
        engine = self.engines[run.agent]
        with run.lock:
            engine.start(run)
            run.event("run_started", {"engine": getattr(engine, "kind", "?")})
        return self.advance(run)

    def advance(self, run: Run) -> Run:
        engine = self.engines[run.agent]
        allowed = set(self.agents[run.agent].get("tools", []))
        tools = self.catalog.list(sorted(allowed))
        with run.lock:
            try:
                while run.status == "running":
                    if run.pending:
                        call = PlannedCall(**run.pending[0])
                        spec = self.catalog.get(call.tool)
                        if spec is None or call.tool not in allowed:
                            self._record(run, engine, call, "ERROR: tool not available to this agent",
                                         ok=False, backend=None, status="refused")
                            continue
                        if self.policy.needs_approval(spec) and call.id not in run.approved:
                            run.status = "awaiting_approval"
                            run.awaiting = {**call.to_dict(), "effect": spec.effect,
                                            "backend": spec.backend, "requested_at": _now()}
                            run.event("approval_requested", {"call_id": call.id, "tool": call.tool})
                            break
                        result = self.catalog.invoke(call.tool, call.args)
                        self.audit.record(run.principal, call.tool, call.args, result, run_id=run.id)
                        self._record(run, engine, call, result.output, ok=result.ok,
                                     backend=result.backend, elapsed_ms=result.elapsed_ms)
                        continue
                    step = engine.next(run, tools)
                    if isinstance(step, Final):
                        run.output = step.text
                        run.status = "succeeded"
                        run.event("run_succeeded")
                    else:
                        run.pending.extend(c.to_dict() for c in step)
            except EngineError as exc:
                run.status, run.error = "failed", str(exc)
                run.event("run_failed", {"error": str(exc)})
            except Exception as exc:  # a broken run must not take the service down
                run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
                run.event("run_failed", {"error": run.error})
            run.updated_at = _now()
        if self.on_settle:
            self.on_settle(run)
        return run

    def decide(self, run: Run, approver: str, approve: bool, reason: str = "") -> Run:
        engine = self.engines[run.agent]
        with run.lock:
            if run.status != "awaiting_approval" or not run.awaiting:
                raise ValueError(f"run {run.id} is {run.status}, not awaiting approval")
            call = PlannedCall(id=run.awaiting["id"], tool=run.awaiting["tool"], args=run.awaiting["args"])
            run.event("approval_decided", {"call_id": call.id, "tool": call.tool,
                                           "decision": "approved" if approve else "rejected",
                                           "by": approver, "reason": reason})
            run.awaiting = None
            run.status = "running"
            if approve:
                run.approved[call.id] = approver
            else:
                note = f"REJECTED by {approver}" + (f": {reason}" if reason else "")
                self._record(run, engine, call,
                             f"{note}. This action was not performed; do not retry it — "
                             "tell the user it needs a different decision.",
                             ok=False, backend=None, status="rejected", decided_by=approver)
        return self.advance(run)

    def cancel(self, run: Run, by: str) -> Run:
        with run.lock:
            if run.status in TERMINAL:
                return run
            run.status, run.awaiting = "cancelled", None
            run.event("run_cancelled", {"by": by})
        if self.on_settle:
            self.on_settle(run)
        return run

    def _record(self, run, engine, call, output, ok, backend, status="done",
                elapsed_ms=0, decided_by=None):
        step = {
            "call_id": call.id,
            "tool": call.tool,
            "args": call.args,
            "backend": backend,
            "status": status,
            "ok": ok,
            "output": output,
            "elapsed_ms": elapsed_ms,
        }
        approver = decided_by or run.approved.get(call.id)
        if approver:
            step["decided_by"] = approver
        run.steps.append(step)
        run.pending = [p for p in run.pending if p["id"] != call.id]
        engine.observe(run, call, output)


class AuditLog:
    """Service-wide record of every tool invocation, direct or inside a run."""

    def __init__(self, limit: int = 5000):
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._limit = limit

    def record(self, principal, tool, args, result, run_id=None) -> None:
        with self._lock:
            self._entries.append({
                "at": _now(),
                "ts": time.time(),
                "principal": principal,
                "run_id": run_id,
                "tool": tool,
                "backend": result.backend,
                "ok": result.ok,
                "elapsed_ms": result.elapsed_ms,
                "args": args,
            })
            del self._entries[: max(0, len(self._entries) - self._limit)]

    def tail(self, limit: int = 100) -> list[dict]:
        return list(self._entries[-limit:])

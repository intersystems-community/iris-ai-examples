"""The HTTP contract. Everything a caller can do, versioned under /v1.

    GET  /healthz                       liveness — the process is up
    GET  /readyz                        readiness — every backend answers
    GET  /v1/service                    what this deployment is (mode, backends)
    GET  /v1/tools                      the tool catalog
    GET  /v1/tools/{tool}
    POST /v1/tools/{tool}/invoke        call one tool, no agent, no model
    GET  /v1/agents
    GET  /v1/agents/{agent}
    POST /v1/agents/{agent}/runs        start a run (wait for it, or poll)
    GET  /v1/runs                       list runs (?status=awaiting_approval)
    GET  /v1/runs/{run}
    POST /v1/runs/{run}/approval        approve or reject the gated call
    POST /v1/runs/{run}/cancel
    GET  /v1/audit                      every tool invocation, newest last

Authentication is an API key (``Authorization: Bearer <key>`` or
``X-API-Key``) mapped to a principal and roles in the config. That is the
prototype's stand-in for an IdP; DESIGN.md says what replaces it.
"""

from __future__ import annotations

import os
import threading
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .catalog import Catalog
from .config import ServiceConfig, load_config
from .engines import build_engine
from .policy import Policy
from .runs import TERMINAL, AuditLog, InMemoryRunStore, Run, Runner


class InvokeRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    input: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    wait: bool = True
    callback_url: str | None = None


class ApprovalRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = ""
    wait: bool = True


class Service:
    """The assembled service: config -> catalog, engines, policy, runner."""

    def __init__(self, cfg: ServiceConfig, **overrides):
        self.cfg = cfg
        self.catalog = Catalog(cfg, **overrides)
        self.policy = Policy.from_config(cfg)
        self.engines = {
            name: build_engine(name, agent, **overrides) for name, agent in cfg.agents.items()
        }
        self.store = InMemoryRunStore()
        self.audit = AuditLog()
        self._callback_http = httpx.Client(timeout=10, transport=overrides.get("callback_transport"))
        self.runner = Runner(
            self.catalog, self.policy, self.engines, cfg.agents, self.audit, on_settle=self._settled
        )

    # -- callbacks ---------------------------------------------------------

    def callback_allowed(self, url: str) -> bool:
        """Callbacks go only to hosts the operator listed: a run that POSTs its
        output wherever a caller points it is an exfiltration channel."""
        allowed = self.cfg.raw.get("callbacks", {}).get("allowed_hosts", [])
        host = urlparse(url).hostname or ""
        return urlparse(url).scheme in ("http", "https") and host in allowed

    def _settled(self, run: Run) -> None:
        if not run.callback_url or run.status == "running":
            return
        try:
            r = self._callback_http.post(run.callback_url, json=run.public())
            run.event("callback_delivered", {"status_code": r.status_code, "run_status": run.status})
        except httpx.HTTPError as exc:
            run.event("callback_failed", {"error": str(exc), "run_status": run.status})


def create_app(cfg: ServiceConfig | str | os.PathLike | None = None, **overrides) -> FastAPI:
    if cfg is None:
        cfg = os.environ.get("AIHUB_CONFIG", "/etc/aihub/service.yaml")
    if not isinstance(cfg, ServiceConfig):
        cfg = load_config(cfg)
    svc = Service(cfg, **overrides)

    app = FastAPI(
        title="AI Hub Service",
        version=__version__,
        description="Agents as a service for InterSystems IRIS applications.",
    )
    app.state.service = svc

    # -- auth --------------------------------------------------------------

    def principal(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ):
        key = x_api_key
        if not key and authorization and authorization.lower().startswith("bearer "):
            key = authorization[7:].strip()
        p = svc.cfg.principal_for_key(key)
        if p is None:
            raise HTTPException(401, "missing or unknown API key")
        return p

    def require(p, action: str) -> None:
        if not svc.policy.allows(p, action):
            raise HTTPException(403, f"{p.name} lacks a role permitted to {action.replace('_', ' ')}")

    def get_run(run_id: str, p) -> Run:
        run = svc.store.get(run_id)
        # Callers see their own runs; approvers see every run, because the
        # approval queue is theirs to work.
        if run is None or (run.principal != p.name and not svc.policy.allows(p, "approve")):
            raise HTTPException(404, f"no run {run_id}")
        return run

    # -- health ------------------------------------------------------------

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    def readyz():
        backends = svc.catalog.health()
        ok = all(b["ok"] for b in backends.values())
        return JSONResponse({"ready": ok, "backends": backends}, status_code=200 if ok else 503)

    # -- discovery ---------------------------------------------------------

    @app.get("/v1/service")
    def service_info(p=Depends(principal)):
        require(p, "list")
        return {
            "name": svc.cfg.name,
            "mode": svc.cfg.mode,
            "version": __version__,
            "backends": {n: b.kind for n, b in svc.catalog.backends.items()},
            "principal": {"name": p.name, "roles": sorted(p.roles)},
        }

    @app.get("/v1/tools")
    def list_tools(p=Depends(principal)):
        require(p, "list")
        return {"tools": [t.public() for t in svc.catalog.list()]}

    @app.get("/v1/tools/{tool}")
    def get_tool(tool: str, p=Depends(principal)):
        require(p, "list")
        spec = svc.catalog.get(tool)
        if spec is None:
            raise HTTPException(404, f"no tool {tool}")
        return {**spec.public(), "requires_approval_in_runs": svc.policy.needs_approval(spec)}

    @app.post("/v1/tools/{tool}/invoke")
    def invoke_tool(tool: str, body: InvokeRequest, p=Depends(principal)):
        spec = svc.catalog.get(tool)
        if spec is None:
            raise HTTPException(404, f"no tool {tool}")
        # A direct call has no run to park, so a write tool is gated on the
        # caller's own role instead of a second person's approval.
        require(p, "invoke_write_tools" if spec.effect == "write" else "invoke_read_tools")
        result = svc.catalog.invoke(tool, body.args)
        svc.audit.record(p.name, tool, body.args, result)
        return {
            "tool": result.tool,
            "backend": result.backend,
            "ok": result.ok,
            "output": result.output,
            "elapsed_ms": result.elapsed_ms,
        }

    @app.get("/v1/agents")
    def list_agents(p=Depends(principal)):
        require(p, "list")
        return {"agents": [_agent_public(n, a, svc) for n, a in svc.cfg.agents.items()]}

    @app.get("/v1/agents/{agent}")
    def get_agent(agent: str, p=Depends(principal)):
        require(p, "list")
        if agent not in svc.cfg.agents:
            raise HTTPException(404, f"no agent {agent}")
        return _agent_public(agent, svc.cfg.agents[agent], svc)

    # -- runs --------------------------------------------------------------

    @app.post("/v1/agents/{agent}/runs")
    def start_run(agent: str, body: RunRequest, p=Depends(principal)):
        require(p, "run_agents")
        if agent not in svc.cfg.agents:
            raise HTTPException(404, f"no agent {agent}")
        if body.callback_url and not svc.callback_allowed(body.callback_url):
            raise HTTPException(422, "callback_url host is not in callbacks.allowed_hosts")
        run = Run(agent=agent, input=body.input, context=body.context, principal=p.name,
                  callback_url=body.callback_url)
        problems = getattr(svc.engines[agent], "validate", lambda r: [])(run)
        if problems:
            raise HTTPException(422, "; ".join(problems))
        svc.store.put(run)
        if body.wait:
            svc.runner.start(run)
            return run.public()
        threading.Thread(target=svc.runner.start, args=(run,), daemon=True).start()
        return JSONResponse(run.public(), status_code=202)

    @app.get("/v1/runs")
    def list_runs(status: str | None = Query(default=None), p=Depends(principal)):
        require(p, "list")
        mine = None if svc.policy.allows(p, "approve") else p.name
        return {"runs": [_run_summary(r) for r in svc.store.list(status=status, principal=mine)]}

    @app.get("/v1/runs/{run_id}")
    def read_run(run_id: str, p=Depends(principal)):
        return get_run(run_id, p).public()

    @app.post("/v1/runs/{run_id}/approval")
    def decide(run_id: str, body: ApprovalRequest, p=Depends(principal)):
        require(p, "approve")
        run = get_run(run_id, p)
        if run.status != "awaiting_approval":
            raise HTTPException(409, f"run {run_id} is {run.status}, not awaiting approval")
        if run.principal == p.name and not svc.cfg.policy.get("approval", {}).get("allow_self_approval"):
            raise HTTPException(403, "a run's own requester cannot approve its gated calls")
        approve = body.decision == "approve"
        if body.wait:
            svc.runner.decide(run, p.name, approve, body.reason)
            return run.public()
        threading.Thread(target=svc.runner.decide, args=(run, p.name, approve, body.reason),
                         daemon=True).start()
        return JSONResponse(run.public(), status_code=202)

    @app.post("/v1/runs/{run_id}/cancel")
    def cancel(run_id: str, p=Depends(principal)):
        run = get_run(run_id, p)
        if run.status in TERMINAL:
            raise HTTPException(409, f"run {run_id} is already {run.status}")
        return svc.runner.cancel(run, p.name).public()

    @app.get("/v1/audit")
    def audit(limit: int = Query(default=100, le=5000), p=Depends(principal)):
        require(p, "approve")
        return {"entries": svc.audit.tail(limit)}

    @app.exception_handler(ValueError)
    def value_error(_req: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    return app


def _agent_public(name: str, agent: dict, svc: Service) -> dict:
    tools = svc.catalog.list(agent.get("tools", []))
    return {
        "name": name,
        "description": agent.get("description", ""),
        "engine": agent.get("engine", "playbook"),
        "requires": agent.get("playbook", {}).get("requires", []),
        "tools": [
            {"name": t.name, "effect": t.effect, "backend": t.backend,
             "requires_approval": svc.policy.needs_approval(t)}
            for t in tools
        ],
    }


def _run_summary(run: Run) -> dict:
    return {
        "id": run.id,
        "agent": run.agent,
        "status": run.status,
        "principal": run.principal,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "awaiting_approval": run.awaiting,
    }

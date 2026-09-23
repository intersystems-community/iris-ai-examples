"""Playbook engine: a declared, deterministic sequence of tool calls.

Many integrations do not want a model choosing steps at all — they want the
agent's *tools* and the service's governance around a known workflow. A
playbook is that: each step names a tool, templated arguments, and an optional
``when:`` condition over the run context and earlier results.

    playbook:
      requires: [patientId]
      steps:
        - tool: FetchPatientSummary
          args: {patientId: "${context.patientId}"}
        - tool: TriggerFollowUp
          when: context.followUp or result.AssessSDoHRisk contains 'URGENT'
          args: {patientId: "${context.patientId}"}
      output: "${result.AssessSDoHRisk}"

Results are keyed by tool name (``result.<Tool>``); a step can set ``as:`` to
keep two calls of the same tool apart.

A step whose tool answers ``ERROR`` fails the run. Later steps take earlier
results as arguments, so carrying on would hand error text to the next tool as
if it were data — a care plan drafted from "ERROR: ..." as the patient's
scores. A rejected approval is a decision, not an error, and does not stop it.
"""

from __future__ import annotations

from ..templating import render, truthy
from . import EngineError, Final, PlannedCall


class PlaybookEngine:
    kind = "playbook"

    def __init__(self, name: str, agent: dict):
        self.name = name
        self.playbook = agent.get("playbook") or {}
        self.steps = self.playbook.get("steps", [])
        if not self.steps:
            raise ValueError(f"agent {name}: a playbook agent needs playbook.steps")

    def validate(self, run) -> list[str]:
        missing = [k for k in self.playbook.get("requires", []) if not run.context.get(k)]
        return [f"context.{k} is required by this playbook" for k in missing]

    def start(self, run) -> None:
        run.engine_state = {"next_step": 0, "results": {}, "keys": {}}

    def _scope(self, run) -> dict:
        return {
            "context": run.context,
            "input": run.input,
            "result": run.engine_state["results"],
        }

    def next(self, run, tools=None):
        state = run.engine_state
        while state["next_step"] < len(self.steps):
            i = state["next_step"]
            step = self.steps[i]
            state["next_step"] = i + 1
            scope = self._scope(run)
            try:
                applies = truthy(step.get("when"), scope)
            except ValueError as exc:
                raise EngineError(f"playbook step {i + 1}: {exc}") from exc
            if not applies:
                run.event("step_skipped", {"step": i + 1, "tool": step["tool"], "when": step.get("when")})
                continue
            call = PlannedCall.new(step["tool"], render(step.get("args", {}), scope))
            state["keys"][call.id] = step.get("as", step["tool"])
            return [call]
        template = self.playbook.get("output")
        if template:
            return Final(str(render(template, self._scope(run))))
        last = list(state["results"].values())
        return Final(last[-1] if last else "")

    def observe(self, run, call: PlannedCall, output: str) -> None:
        key = run.engine_state["keys"].get(call.id, call.tool)
        run.engine_state["results"][key] = output
        if output.startswith("ERROR"):
            raise EngineError(f"playbook step {call.tool} failed: {output}")

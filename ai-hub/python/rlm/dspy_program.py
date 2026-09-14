"""DSPy-style orchestration program for RLM flows.

This module intentionally supports running without the DSPy package installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .toolset import RLMToolSet

try:  # pragma: no cover - optional dependency
    import dspy  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    dspy = None


DEFAULT_MAX_DEPTH = 5
MIN_MAX_DEPTH = 1
MAX_MAX_DEPTH = 8


class ProgramStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class StageType(str, Enum):
    DECOMPOSE = "decompose"
    EXPLORE = "explore"
    SUMMARIZE = "summarize"
    FINALIZE = "finalize"


class StageOutcome(str, Enum):
    SUCCESS = "success"
    RETRYABLE_ERROR = "retryable_error"
    TERMINAL_ERROR = "terminal_error"


@dataclass
class StageTraceEvent:
    stage_type: StageType
    outcome: StageOutcome
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ExplorationProgramState:
    query: str
    context_reference: str
    context: str
    max_depth: int = DEFAULT_MAX_DEPTH
    current_depth: int = 0
    status: ProgramStatus = ProgramStatus.RUNNING
    traces: List[StageTraceEvent] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)


if dspy is not None:  # pragma: no cover - runtime dependent
    class RLMContextExplorer(dspy.Signature):
        """Explore a large context stored in IRIS and answer a query recursively."""

        context_id = dspy.InputField(desc="Reference to the large context in IRIS")
        query = dspy.InputField(desc="The user's question")
        history = dspy.InputField(desc="Previous exploration steps and findings")
        answer = dspy.OutputField(desc="The final answer or a new exploration plan")
else:
    class RLMContextExplorer:  # pragma: no cover - simple placeholder used in tests
        """Fallback signature placeholder when DSPy is unavailable."""

        context_id: str
        query: str
        history: str
        answer: str


class RLMPyModule:
    """DSPy-style module with deterministic fallback orchestration."""

    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH):
        if not (MIN_MAX_DEPTH <= max_depth <= MAX_MAX_DEPTH):
            raise ValueError(f"max_depth must be between {MIN_MAX_DEPTH} and {MAX_MAX_DEPTH}")
        self.max_depth = max_depth
        self.stage_handlers: Dict[StageType, Callable[[ExplorationProgramState, RLMToolSet], Any]] = {
            StageType.DECOMPOSE: self._decompose,
            StageType.EXPLORE: self._explore,
            StageType.SUMMARIZE: self._summarize,
            StageType.FINALIZE: self._finalize,
        }

    def set_stage_handler(
        self,
        stage: StageType,
        handler: Callable[[ExplorationProgramState, RLMToolSet], Any],
    ) -> None:
        self.stage_handlers[stage] = handler

    def forward(
        self,
        context_reference: str,
        query: str,
        *,
        history: str = "",
        toolset: Optional[RLMToolSet] = None,
        context: str = "",
    ) -> Dict[str, Any]:
        if toolset is None:
            raise ValueError("toolset is required")

        if context_reference.startswith("session:"):
            session_id = context_reference.split(":", 1)[1]
            snapshot = RLMToolSet.load_session_snapshot(session_id) or {}
            working_context = str(snapshot.get("context", context))
        else:
            working_context = context or toolset.session.context

        working_context = toolset.prepare_payload_for_reasoning(working_context)
        if working_context.startswith("FAIL_CLOSED:"):
            trace = StageTraceEvent(
                stage_type=StageType.EXPLORE,
                outcome=StageOutcome.TERMINAL_ERROR,
                detail=working_context,
            )
            return {
                "decision_type": "fail_closed",
                "answer": "",
                "remediation_guidance": working_context,
                "traces": [trace],
                "status": ProgramStatus.FAILED.value,
                "confidence": 0.0,
            }

        state = ExplorationProgramState(
            query=query,
            context_reference=context_reference,
            context=working_context,
            max_depth=self.max_depth,
        )

        for stage in [StageType.DECOMPOSE, StageType.EXPLORE, StageType.SUMMARIZE, StageType.FINALIZE]:
            handler = self.stage_handlers[stage]
            handler(state, toolset)
            if state.status in (ProgramStatus.FAILED, ProgramStatus.BLOCKED, ProgramStatus.COMPLETED):
                if stage == StageType.FINALIZE:
                    break

        answer = state.findings[-1] if state.findings else ""
        confidence = self._confidence_score(answer)
        if not answer or confidence < 0.35:
            plan = "PLAN: refine query and continue staged exploration"
            state.traces.append(StageTraceEvent(StageType.FINALIZE, StageOutcome.SUCCESS, plan))
            return {
                "decision_type": "next_step_plan",
                "answer": plan,
                "traces": state.traces,
                "status": ProgramStatus.COMPLETED.value,
                "confidence": confidence,
            }

        return {
            "decision_type": "answer",
            "answer": answer,
            "traces": state.traces,
            "status": ProgramStatus.COMPLETED.value,
            "confidence": confidence,
        }

    def _decompose(self, state: ExplorationProgramState, toolset: RLMToolSet) -> None:
        subtasks = [item.strip() for item in state.query.split(" and ") if item.strip()]
        state.subtasks = subtasks or [state.query]
        state.traces.append(
            StageTraceEvent(
                stage_type=StageType.DECOMPOSE,
                outcome=StageOutcome.SUCCESS,
                detail=f"subtasks={len(state.subtasks)}",
            )
        )
        toolset.emit_stage_trace("decompose", "success", f"subtasks={len(state.subtasks)}")

    def _explore(self, state: ExplorationProgramState, toolset: RLMToolSet) -> None:
        snippets: List[str] = []
        for task in state.subtasks:
            snippets.append(toolset.execute("search_context", {"query": task, "top_k": 3}))
        merged = "\n\n".join(snippets)
        state.findings.append(merged)
        state.traces.append(StageTraceEvent(StageType.EXPLORE, StageOutcome.SUCCESS, "searched context"))
        toolset.emit_stage_trace("explore", "success", "searched context")

    def _summarize(self, state: ExplorationProgramState, toolset: RLMToolSet) -> None:
        if not state.findings:
            state.traces.append(StageTraceEvent(StageType.SUMMARIZE, StageOutcome.RETRYABLE_ERROR, "no findings"))
            toolset.emit_stage_trace("summarize", "retryable_error", "no findings")
            return
        text = state.findings[-1]
        summary_lines = [line for line in text.splitlines() if line.strip()][:8]
        summary = "\n".join(summary_lines)
        state.findings.append(summary)
        state.traces.append(StageTraceEvent(StageType.SUMMARIZE, StageOutcome.SUCCESS, "created summary"))
        toolset.emit_stage_trace("summarize", "success", "created summary")

    def _finalize(self, state: ExplorationProgramState, toolset: RLMToolSet) -> None:
        result = state.findings[-1] if state.findings else ""
        if not result:
            state.status = ProgramStatus.FAILED
            state.traces.append(StageTraceEvent(StageType.FINALIZE, StageOutcome.TERMINAL_ERROR, "empty result"))
            toolset.emit_stage_trace("finalize", "terminal_error", "empty result")
            return

        concise = result[:1200]
        state.findings.append(concise)
        state.status = ProgramStatus.COMPLETED
        state.traces.append(StageTraceEvent(StageType.FINALIZE, StageOutcome.SUCCESS, "final answer ready"))
        toolset.emit_stage_trace("finalize", "success", "final answer ready")

    @staticmethod
    def _confidence_score(answer: str) -> float:
        if not answer:
            return 0.0
        if "No relevant sections" in answer:
            return 0.2
        if len(answer) < 60:
            return 0.4
        return 0.75

"""RLM Agent - High-level API for Recursive Language Model agents."""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import json
import os

from iris_llm import Agent, Provider

from .dspy_program import RLMPyModule, DEFAULT_MAX_DEPTH, MIN_MAX_DEPTH, MAX_MAX_DEPTH
from .toolset import RLMToolSet
from .prompts import RLM_SYSTEM_PROMPT


@dataclass
class RLMResult:
    """Result from an RLM agent run."""

    answer: str
    session_id: str
    iterations: int = 0
    vars: Dict[str, str] = field(default_factory=dict)
    total_tokens: int = 0
    success: bool = True
    error: Optional[str] = None
    outcome_class: str = "answer"
    quality_score: Optional[float] = None
    remediation_guidance: Optional[str] = None
    stage_traces: List[Dict[str, Any]] = field(default_factory=list)


class RLMAgent:
    """High-level RLM agent interface."""

    def __init__(
        self,
        provider: Optional[Provider] = None,
        model: str = "gpt-4o",
        max_depth: int = DEFAULT_MAX_DEPTH,
        system_prompt: Optional[str] = None,
        sandbox_mode: str = "disabled",
        max_output_chars: int = 4000,
        max_output_tokens: int = 1000,
        execute_timeout_seconds: int = 30,
        use_dspy: bool = False,
        quality_threshold: float = 4.0,
    ):
        if provider is None:
            provider = Provider("openai", json.dumps({"api_key": os.environ.get("OPENAI_API_KEY", "")}))

        self.provider = provider
        self.model = model
        self.max_depth = max_depth
        self.system_prompt = system_prompt or RLM_SYSTEM_PROMPT
        self.sandbox_mode = sandbox_mode
        self.max_output_chars = max_output_chars
        self.max_output_tokens = max_output_tokens
        self.execute_timeout_seconds = execute_timeout_seconds
        self.use_dspy = use_dspy
        self.quality_threshold = quality_threshold

    def evaluate_parity_gate(
        self,
        outcome_parity: bool,
        quality_score: Optional[float],
        quality_threshold: Optional[float] = None,
    ) -> bool:
        threshold = self.quality_threshold if quality_threshold is None else quality_threshold
        return bool(outcome_parity and quality_score is not None and quality_score >= threshold)

    def _score_answer_quality(self, query: str, answer: str, context: str) -> float:
        """Simple deterministic quality scorer used by parity gate tests."""
        if not answer.strip():
            return 0.0
        score = 1.0
        if len(answer) >= 40:
            score += 1.0
        query_tokens = {t for t in query.lower().split() if len(t) > 3}
        answer_tokens = set(answer.lower().split())
        overlap = len(query_tokens.intersection(answer_tokens))
        if query_tokens:
            score += min(2.0, 2.0 * (overlap / max(1, len(query_tokens))))
        if len(context) > 0:
            score += 1.0
        return min(5.0, score)

    def _build_toolset(
        self,
        *,
        context: str,
        session_id: Optional[str],
        external_tools: Optional[Dict[str, Any]],
    ) -> RLMToolSet:
        return RLMToolSet(
            context=context,
            provider=self.provider,
            model=self.model,
            session_id=session_id,
            max_depth=self.max_depth,
            external_tools=external_tools,
            sandbox_mode=self.sandbox_mode,
            max_output_chars=self.max_output_chars,
            max_output_tokens=self.max_output_tokens,
            execute_timeout_seconds=self.execute_timeout_seconds,
        )

    def _run_legacy_flow(self, query: str, toolset: RLMToolSet) -> str:
        agent = Agent.with_provider(self.model, self.provider)
        # Give the toolset a reference to the parent agent so that
        # sub-agents created via spawn_subagent / summarize_var can
        # use create_child_agent to share the tokio runtime.
        toolset.parent_agent = agent
        agent.add_tool_set(toolset)
        agent.set_system_prompt(self.system_prompt)
        result = agent.run(query)

        if toolset.is_finalized:
            return toolset.final_result or result
        return result

    def _run_dspy_flow(self, query: str, context: str, toolset: RLMToolSet) -> Dict[str, Any]:
        if not (MIN_MAX_DEPTH <= self.max_depth <= MAX_MAX_DEPTH):
            raise ValueError(f"max_depth must be between {MIN_MAX_DEPTH} and {MAX_MAX_DEPTH}")

        module = RLMPyModule(max_depth=self.max_depth)
        payload = module.forward(
            context_reference=f"session:{toolset.session.session_id}",
            query=query,
            history="",
            toolset=toolset,
            context=context,
        )
        return payload

    def run(
        self,
        query: str,
        context: str,
        session_id: Optional[str] = None,
        max_iterations: int = 50,
        external_tools: Optional[Dict[str, Any]] = None,
    ) -> RLMResult:
        del max_iterations  # preserved for API compatibility
        toolset = self._build_toolset(context=context, session_id=session_id, external_tools=external_tools)

        try:
            if self.use_dspy:
                payload = self._run_dspy_flow(query, context, toolset)
                answer = str(payload.get("answer", ""))
                outcome_class = str(payload.get("decision_type", "answer"))
                remediation = payload.get("remediation_guidance")
                quality = self._score_answer_quality(query, answer, context)
                parity_ok = self.evaluate_parity_gate(True, quality)
                if not parity_ok and outcome_class == "answer":
                    outcome_class = "next_step_plan"
                    answer = "PLAN: parity gate did not pass quality threshold"

                return RLMResult(
                    answer=answer,
                    session_id=toolset.session.session_id,
                    iterations=toolset.session.iteration_count,
                    vars=toolset.session.vars,
                    total_tokens=toolset.session.total_tokens,
                    success=True,
                    outcome_class=outcome_class,
                    quality_score=quality,
                    remediation_guidance=remediation,
                    stage_traces=list(getattr(toolset.session, "stage_traces", [])),
                )

            answer = self._run_legacy_flow(query, toolset)
            return RLMResult(
                answer=answer,
                session_id=toolset.session.session_id,
                iterations=toolset.session.iteration_count,
                vars=toolset.session.vars,
                total_tokens=toolset.session.total_tokens,
                success=True,
                outcome_class="answer",
                quality_score=self._score_answer_quality(query, answer, context),
                stage_traces=list(getattr(toolset.session, "stage_traces", [])),
            )

        except TimeoutError:
            return RLMResult(
                answer="",
                session_id=toolset.session.session_id,
                success=False,
                error=f"RLM agent timed out after {self.execute_timeout_seconds}s",
            )
        except Exception as e:
            return RLMResult(
                answer="",
                session_id=toolset.session.session_id,
                success=False,
                error=str(e),
                outcome_class="failure",
                stage_traces=list(getattr(toolset.session, "stage_traces", [])),
            )

    def resume(
        self,
        session_id: str,
        query: str,
        external_tools: Optional[Dict[str, Any]] = None,
    ) -> RLMResult:
        snapshot = RLMToolSet.load_session_snapshot(session_id)
        if snapshot is None:
            return RLMResult(
                answer="",
                session_id=session_id,
                success=False,
                error=f"Session {session_id} not found",
                outcome_class="failure",
            )

        return self.run(
            query=query,
            context=str(snapshot.get("context", "")),
            session_id=session_id,
            external_tools=external_tools,
        )


def create_rlm_agent(
    provider_type: str = "openai",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    **kwargs,
) -> RLMAgent:
    if provider_type == "openai":
        provider = Provider("openai", json.dumps({"api_key": api_key}))
    elif provider_type == "anthropic":
        provider = Provider("anthropic", json.dumps({"api_key": api_key}))
    elif provider_type == "bedrock":
        provider = Provider("bedrock", '{"region": "us-east-1"}')
    elif provider_type == "nim":
        provider = Provider("nim", json.dumps({"api_key": api_key}))
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")

    return RLMAgent(provider=provider, model=model, **kwargs)

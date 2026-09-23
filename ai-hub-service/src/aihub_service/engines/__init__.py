"""Agent engines: what decides the next tool call.

An engine is step-based and keeps its whole state in ``run.engine_state``
(plain JSON), so a run can stop mid-flight for a human approval — minutes or
days — and resume where it was. Three engines ship:

    playbook   a declared sequence of tool calls with conditions. No model, no
               key, fully deterministic: the right choice for a workflow whose
               steps are known and whose value is in the tools and the audit.
    openai     any OpenAI-compatible chat-completions endpoint (OpenAI, Azure
               OpenAI, vLLM, Ollama) driving a tool-calling loop.
    anthropic  the Anthropic Messages API driving the same loop.

An engine returns either a list of ``PlannedCall`` or a ``Final``; the run
lifecycle in runs.py owns execution, policy, and the audit trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class PlannedCall:
    id: str
    tool: str
    args: dict

    @classmethod
    def new(cls, tool: str, args: dict, id: str | None = None) -> "PlannedCall":
        return cls(id=id or f"call_{uuid.uuid4().hex[:12]}", tool=tool, args=args or {})

    def to_dict(self) -> dict:
        return {"id": self.id, "tool": self.tool, "args": self.args}


@dataclass
class Final:
    text: str


class EngineError(RuntimeError):
    pass


def build_engine(agent_name: str, agent: dict, **overrides):
    kind = agent.get("engine", "playbook")
    if kind == "playbook":
        from .playbook import PlaybookEngine

        return PlaybookEngine(agent_name, agent)
    if kind == "openai":
        from .llm import OpenAIEngine

        return OpenAIEngine(agent_name, agent, transport=overrides.get("http_transport"))
    if kind == "anthropic":
        from .llm import AnthropicEngine

        return AnthropicEngine(agent_name, agent, transport=overrides.get("http_transport"))
    raise ValueError(f"agent {agent_name}: unknown engine {kind!r} (want playbook, openai or anthropic)")

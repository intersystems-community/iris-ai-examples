"""Optional LangGraph workflow scaffolding for RLM integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from iris_llm.langchain import ChatIris, IrisTool


@dataclass
class WorkflowState:
    """Serializable graph state for plan/execute/replan cycles."""

    session_id: str
    input: str
    plan: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    output: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LangGraphWorkflow:
    """Container for optional graph workflow components."""

    llm: ChatIris
    tools: List[IrisTool]
    graph: Optional[Any] = None

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder invocation API for future LangGraph state graph runtime."""
        # This scaffolding keeps the public contract stable even before wiring
        # concrete LangGraph nodes/checkpointer in post-MVP work.
        return dict(state)


def build_workflow(
    chat_iris: ChatIris,
    toolset: Any,
    persisted_state: Optional[Dict[str, Any]] = None,
) -> LangGraphWorkflow:
    """Create a workflow shell with ChatIris and IrisTool bindings."""
    tools = [IrisTool.from_toolset(toolset)]
    workflow = LangGraphWorkflow(llm=chat_iris, tools=tools, graph=None)
    if persisted_state is not None:
        # Reserved for IRIS-backed state rehydration once graph runtime is wired.
        _ = persisted_state
    return workflow

"""
iris_rlm - Recursive Language Model Agent for IRIS %AI

RLM agents treat large contexts as an external environment that the LLM
manipulates programmatically, rather than stuffing into the prompt window.
"""

from .toolset import RLMToolSet
from .agent import RLMAgent, RLMResult
from .prompts import RLM_SYSTEM_PROMPT, RLM_SUBAGENT_PROMPT
from .dspy_program import (
    RLMPyModule,
    RLMContextExplorer,
    StageType,
    StageOutcome,
    ProgramStatus,
    DEFAULT_MAX_DEPTH,
    MIN_MAX_DEPTH,
    MAX_MAX_DEPTH,
)

try:
    from .langgraph import build_workflow, LangGraphWorkflow
except Exception:  # optional dependency path
    build_workflow = None
    LangGraphWorkflow = None

__version__ = "0.1.0"
__all__ = [
    "RLMToolSet",
    "RLMAgent",
    "RLMResult",
    "RLM_SYSTEM_PROMPT",
    "RLM_SUBAGENT_PROMPT",
    "RLMPyModule",
    "RLMContextExplorer",
    "StageType",
    "StageOutcome",
    "ProgramStatus",
    "DEFAULT_MAX_DEPTH",
    "MIN_MAX_DEPTH",
    "MAX_MAX_DEPTH",
    "build_workflow",
    "LangGraphWorkflow",
]

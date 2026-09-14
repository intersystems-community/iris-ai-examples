"""Adapter helpers for DSPy-style orchestration over existing provider interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class DSPYProviderAdapter:
    """Thin adapter that can proxy model calls to existing provider-backed agents."""

    provider: Any
    model: str

    def call(self, query: str, context: str, system_prompt: str = "") -> str:
        """Return a deterministic fallback response when no DSPy runtime is present."""
        prompt_prefix = f"[{self.model}] " if self.model else ""
        if system_prompt:
            return f"{prompt_prefix}{query}\n\n{context[:1200]}"
        return f"{prompt_prefix}{query}\n\n{context[:1200]}"


class DSPYLMAdapter:
    """Wrapper intended for use by DSPy modules without hard dependency on DSPy runtime."""

    def __init__(self, provider: Any, model: str):
        self.provider = provider
        self.model = model
        self._adapter = DSPYProviderAdapter(provider=provider, model=model)

    def infer(self, query: str, context: str, system_prompt: str = "") -> str:
        return self._adapter.call(query=query, context=context, system_prompt=system_prompt)


def run_with_agent_factory(
    agent_factory: Callable[[], Any],
    query: str,
    *,
    on_error: Optional[Callable[[Exception], str]] = None,
) -> str:
    """Run a query through a provided agent factory with safe fallback behavior."""
    try:
        agent = agent_factory()
        return str(agent.run(query))
    except Exception as exc:  # pragma: no cover - defensive fallback path
        if on_error is not None:
            return on_error(exc)
        return f"ERROR: DSPY adapter execution failed: {exc}"

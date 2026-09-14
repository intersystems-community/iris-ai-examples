#!/usr/bin/env python3
"""Single-command RLM demo entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from iris_rlm import RLMAgent
except Exception:
    from agent import RLMAgent
from iris_llm import Provider


SAMPLE_CONTEXT = """
Project summary:
- Build an RLM agent MVP.
- Validate fallback behavior without optional dependencies.
- Track session metadata and support finalize output.
"""


def _build_provider(provider_name: str):
    if provider_name == "openai":
        return Provider("openai", json.dumps({"api_key": os.environ.get("OPENAI_API_KEY", "")}))
    if provider_name == "anthropic":
        return Provider("anthropic", json.dumps({"api_key": os.environ.get("ANTHROPIC_API_KEY", "")}))
    raise ValueError(f"Unsupported provider: {provider_name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run an RLM demo query. Provide context via --sample-context or stdin. "
            "Expected output is concise answer + metadata line with session, iterations, and token estimate."
        )
    )
    parser.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--query", default="Summarize the key goals in 3 bullets.")
    parser.add_argument("--sample-context", action="store_true", help="Use built-in sample context.")
    parser.add_argument(
        "--sandbox-mode",
        default="disabled",
        choices=["disabled", "restricted"],
        help="Enable restricted execute_python sandbox if needed for advanced workflows.",
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=4000,
        help="Threshold for storing long tool outputs as variables instead of inline returns.",
    )
    args = parser.parse_args(argv)

    context = SAMPLE_CONTEXT if args.sample_context else sys.stdin.read()
    if not context.strip():
        print("ERROR: Provide context via stdin or use --sample-context")
        return 2

    provider = _build_provider(args.provider)
    agent = RLMAgent(
        provider=provider,
        model=args.model,
        sandbox_mode=args.sandbox_mode,
        max_output_chars=args.max_output_chars,
    )
    result = agent.run(query=args.query, context=context)

    if not result.success:
        print(f"ERROR: {result.error}")
        return 1

    print(result.answer)
    print(f"\n[session={result.session_id} iterations={result.iterations} tokens~{result.total_tokens}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

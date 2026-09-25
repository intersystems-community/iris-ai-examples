"""Provider settings shared with Demo.AIHub.Chat, which reads the same variables.

DEMO_LLM_BASE_URL switches the openai provider to any OpenAI-compatible server
(Ollama, vLLM); DEMO_MODEL names the model. Unset, both tabs use OpenAI.
"""

import json
from typing import Mapping, Tuple


def from_env(env: Mapping[str, str]) -> Tuple[str, str]:
    """(model, provider settings JSON) for iris_llm.Provider("openai", ...)."""
    base_url = env.get("DEMO_LLM_BASE_URL", "")
    settings = {"api_key": env.get("OPENAI_API_KEY") or "unused"}
    if base_url:
        settings["base_url"] = base_url
    return env.get("DEMO_MODEL") or "gpt-4o-mini", json.dumps(settings)

"""Model-driven engines: an LLM chooses the tool calls.

Plain HTTP (httpx) against the providers' public APIs rather than their SDKs:
the service image stays small, and a test can hand the engine an
``httpx.MockTransport`` and script the model's replies exactly.

The conversation lives in ``run.engine_state["messages"]`` so a run that parks
for approval resumes with the model's full context intact.
"""

from __future__ import annotations

import json

import httpx

from . import EngineError, Final, PlannedCall

DEFAULT_MAX_TURNS = 12


def _user_message(run) -> str:
    text = run.input or "Run your workflow for the context given."
    if run.context:
        text += "\n\nContext (JSON):\n" + json.dumps(run.context, indent=2)
    return text


class _LLMEngine:
    def __init__(self, name: str, agent: dict, transport: httpx.BaseTransport | None = None):
        self.name = name
        self.agent = agent
        self.model = agent.get("model")
        self.instructions = agent.get("instructions", "")
        self.max_tokens = int(agent.get("max_tokens", 1500))
        self.max_turns = int(agent.get("max_turns", DEFAULT_MAX_TURNS))
        self._http = httpx.Client(timeout=float(agent.get("timeout", 120)), transport=transport)
        if not self.model:
            raise ValueError(f"agent {name}: engine {self.kind} needs a model")

    def validate(self, run) -> list[str]:
        if not self.agent.get("api_key") and self.kind == "anthropic":
            return ["this agent's engine has no api_key configured"]
        return []

    def _post(self, url: str, headers: dict, body: dict) -> dict:
        try:
            r = self._http.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise EngineError(f"{self.kind}: {type(exc).__name__}: {exc}") from exc
        if r.status_code >= 400:
            # A bodiless 500 from an OpenAI-compatible endpoint has three causes
            # (bad base URL, unknown model, rejected key); name all three.
            detail = r.text[:300] or "(empty body: check base_url, model name and api key)"
            raise EngineError(f"{self.kind}: HTTP {r.status_code}: {detail}")
        return r.json()


class OpenAIEngine(_LLMEngine):
    kind = "openai"

    def start(self, run) -> None:
        messages = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        messages.append({"role": "user", "content": _user_message(run)})
        run.engine_state = {"messages": messages, "turns": 0}

    def next(self, run, tools):
        state = run.engine_state
        if state["turns"] >= self.max_turns:
            raise EngineError(f"agent exceeded max_turns={self.max_turns}")
        state["turns"] += 1
        base = (self.agent.get("base_url") or "https://api.openai.com/v1/").rstrip("/")
        headers = {}
        if self.agent.get("api_key"):
            headers["Authorization"] = f"Bearer {self.agent['api_key']}"
        body = {
            "model": self.model,
            "messages": state["messages"],
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        data = self._post(f"{base}/chat/completions", headers, body)
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return Final(msg.get("content") or "")
        state["messages"].append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": calls}
        )
        planned = []
        for c in calls:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            planned.append(PlannedCall.new(c["function"]["name"], args, id=c["id"]))
        return planned

    def observe(self, run, call: PlannedCall, output: str) -> None:
        run.engine_state["messages"].append(
            {"role": "tool", "tool_call_id": call.id, "content": output}
        )


class AnthropicEngine(_LLMEngine):
    kind = "anthropic"
    API_VERSION = "2023-06-01"

    def start(self, run) -> None:
        run.engine_state = {
            "messages": [{"role": "user", "content": _user_message(run)}],
            "pending_results": [],
            "turns": 0,
        }

    def next(self, run, tools):
        state = run.engine_state
        if state["pending_results"]:
            # Every tool_result for one assistant turn goes back in a single user message.
            state["messages"].append({"role": "user", "content": state["pending_results"]})
            state["pending_results"] = []
        if state["turns"] >= self.max_turns:
            raise EngineError(f"agent exceeded max_turns={self.max_turns}")
        state["turns"] += 1
        base = (self.agent.get("base_url") or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": self.agent.get("api_key", ""),
            "anthropic-version": self.API_VERSION,
        }
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": state["messages"],
        }
        if self.instructions:
            body["system"] = self.instructions
        if tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        data = self._post(f"{base}/v1/messages", headers, body)
        content = data.get("content", [])
        uses = [b for b in content if b.get("type") == "tool_use"]
        if data.get("stop_reason") != "tool_use" or not uses:
            return Final("".join(b.get("text", "") for b in content if b.get("type") == "text"))
        state["messages"].append({"role": "assistant", "content": content})
        return [PlannedCall.new(b["name"], b.get("input") or {}, id=b["id"]) for b in uses]

    def observe(self, run, call: PlannedCall, output: str) -> None:
        run.engine_state["pending_results"].append(
            {"type": "tool_result", "tool_use_id": call.id, "content": output}
        )

"""
otel_spans — lightweight OTel span emission for iris_llm agents and tools.

Pure stdlib, no opentelemetry package required. Emits OTLP/HTTP JSON payloads
following gen_ai.* semantic conventions (OpenTelemetry GenAI spec 1.29+).

Usage:

    from otel_spans import OTelEmitter

    emitter = OTelEmitter()          # reads OTEL_* env vars
    trace_id = emitter.new_trace()

    # Around an LLM call:
    t0 = emitter.now_ns()
    response = agent.run(query)
    emitter.chat(trace_id, t0, model="gpt-4o-mini",
                 input_tokens=120, output_tokens=45,
                 completion_text=str(response))

    # Around a tool call (pass the chat span_id as parent):
    t0 = emitter.now_ns()
    result = tool.run(args)
    emitter.tool_call(trace_id, parent_span_id, t0,
                      tool_name="list_namespaces",
                      input_kwargs={}, result=result)

Configure via environment variables (standard OTEL):
    OTEL_EXPORTER_OTLP_ENDPOINT   default: http://localhost:4318
    OTEL_SERVICE_NAME             default: iris-llm-agent
    OTEL_RESOURCE_GEN_AI_SYSTEM   default: openai
"""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OTelEmitter:
    endpoint: str = field(default="")
    service_name: str = field(default="")
    gen_ai_system: str = field(default="")
    capture_content: bool = field(default=False)
    _enabled: bool = field(init=False)

    def __post_init__(self) -> None:
        if not self.endpoint:
            self.endpoint = (
                os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
                .rstrip("/")
            )
        if not self.service_name:
            self.service_name = os.environ.get("OTEL_SERVICE_NAME", "iris-llm-agent")
        if not self.gen_ai_system:
            self.gen_ai_system = os.environ.get(
                "OTEL_RESOURCE_GEN_AI_SYSTEM", "openai"
            )
        self._enabled = bool(self.endpoint)
        if self._enabled:
            self.endpoint = self.endpoint + "/v1/traces"

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── ID / time helpers ────────────────────────────────────────────────────

    @staticmethod
    def new_trace() -> str:
        return secrets.token_hex(16)

    @staticmethod
    def new_span() -> str:
        return secrets.token_hex(8)

    @staticmethod
    def now_ns() -> int:
        return int(time.time() * 1_000_000_000)

    # ── High-level span factories ────────────────────────────────────────────

    def chat(
        self,
        trace_id: str,
        start_ns: int,
        *,
        span_id: str = "",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        end_ns: int = 0,
        parent_span_id: str = "",
        completion_text: str = "",
        session_id: str = "",
    ) -> str:
        """Emit a gen_ai.chat span. Returns the span_id used.

        Pass span_id= when the id must be known before the span ends (e.g. to
        wire tool-call children during the agent loop). When omitted a new id
        is generated. Either way the same id is returned.
        """
        sid = span_id or self.new_span()
        self._emit_chat(
            trace_id=trace_id,
            span_id=sid,
            start_ns=start_ns,
            end_ns=end_ns or self.now_ns(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            parent_span_id=parent_span_id,
            completion_text=completion_text,
            session_id=session_id,
        )
        return sid

    def _emit_chat(
        self,
        *,
        trace_id: str,
        span_id: str,
        start_ns: int,
        end_ns: int,
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        parent_span_id: str = "",
        completion_text: str = "",
        session_id: str = "",
    ) -> None:
        """Low-level gen_ai.chat span emission with explicit span_id."""
        attrs = [
            _str_attr("gen_ai.operation.name", "chat"),
            _str_attr("gen_ai.system", self.gen_ai_system),
        ]
        if input_tokens:
            attrs.append(_int_attr("gen_ai.usage.input_tokens", input_tokens))
        if output_tokens:
            attrs.append(_int_attr("gen_ai.usage.output_tokens", output_tokens))
        if model:
            attrs.append(_str_attr("gen_ai.request.model", model))
        if session_id:
            attrs.append(_str_attr("session.id", session_id))

        events = None
        if self.capture_content and completion_text:
            events = [_completion_event(completion_text)]

        self._emit(
            name="gen_ai.chat",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            start_ns=start_ns,
            end_ns=end_ns,
            attrs=attrs,
            events=events,
            status_code=0,
        )

    def tool_call(
        self,
        trace_id: str,
        parent_span_id: str,
        start_ns: int,
        *,
        tool_name: str,
        input_kwargs: dict | None = None,
        result: str = "",
        end_ns: int = 0,
        error: str = "",
        call_id: str = "",
        session_id: str = "",
    ) -> str:
        """Emit a gen_ai.tool_call span. Returns the new span_id."""
        span_id = self.new_span()
        attrs = [
            _str_attr("gen_ai.operation.name", "tool_call"),
            _str_attr("gen_ai.tool.name", tool_name),
            _str_attr("gen_ai.system", self.gen_ai_system),
        ]
        if call_id:
            attrs.append(_str_attr("gen_ai.tool.call_id", call_id))
        if session_id:
            attrs.append(_str_attr("session.id", session_id))
        if input_kwargs is not None:
            attrs.append(_str_attr("gen_ai.tool.input", json.dumps(input_kwargs)))
        if result:
            attrs.append(_str_attr("gen_ai.tool.output", result[:500]))
        if error:
            attrs.append(_str_attr("gen_ai.tool.error", error[:200]))

        self._emit(
            name=f"execute_tool {tool_name}",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            start_ns=start_ns,
            end_ns=end_ns or self.now_ns(),
            attrs=attrs,
            status_code=2 if error else 0,
        )
        return span_id

    def agent_turn(
        self,
        trace_id: str,
        start_ns: int,
        *,
        query: str = "",
        end_ns: int = 0,
        parent_span_id: str = "",
    ) -> str:
        """Emit a gen_ai.agent_turn root span wrapping a full query/response cycle."""
        span_id = self.new_span()
        attrs = [_str_attr("gen_ai.operation.name", "agent_turn")]
        if self.capture_content and query:
            attrs.append(_str_attr("gen_ai.input.query", query[:500]))
        self._emit(
            name="gen_ai.agent_turn",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            start_ns=start_ns,
            end_ns=end_ns or self.now_ns(),
            attrs=attrs,
            status_code=0,
        )
        return span_id

    # ── Context manager for a tool call ─────────────────────────────────────

    def tool_span(
        self,
        trace_id: str,
        parent_span_id: str,
        tool_name: str,
        input_kwargs: dict | None = None,
    ) -> "_ToolSpan":
        """Context manager that emits a tool_call span on exit.

        with emitter.tool_span(trace_id, chat_span_id, "list_namespaces") as span:
            result = ts.execute("list_namespaces", {})
            span.result = result
        """
        return _ToolSpan(self, trace_id, parent_span_id, tool_name, input_kwargs)

    # ── Low-level emit ───────────────────────────────────────────────────────

    def _emit(
        self,
        *,
        name: str,
        trace_id: str,
        span_id: str,
        parent_span_id: str,
        start_ns: int,
        end_ns: int,
        attrs: list[dict],
        events: list[dict] | None = None,
        status_code: int = 1,
    ) -> None:
        if not self._enabled:
            return

        span: dict[str, Any] = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": name,
            "kind": 3,
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(end_ns),
            "attributes": attrs,
            "status": {"code": status_code},
        }
        if parent_span_id:
            span["parentSpanId"] = parent_span_id
        if events:
            span["events"] = events

        payload = {
            "resourceSpans": [{
                "resource": {"attributes": [
                    _str_attr("service.name", self.service_name),
                    _str_attr("gen_ai.system", self.gen_ai_system),
                ]},
                "scopeSpans": [{"scope": {"name": "iris-llm"}, "spans": [span]}],
            }]
        }

        body = json.dumps(payload).encode()
        try:
            req = urllib.request.Request(
                self.endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass  # OTel emission is always non-fatal


class _ToolSpan:
    """Context manager returned by OTelEmitter.tool_span()."""

    def __init__(
        self,
        emitter: OTelEmitter,
        trace_id: str,
        parent_span_id: str,
        tool_name: str,
        input_kwargs: dict | None,
    ) -> None:
        self._emitter = emitter
        self._trace_id = trace_id
        self._parent_span_id = parent_span_id
        self._tool_name = tool_name
        self._input_kwargs = input_kwargs
        self._start_ns = emitter.now_ns()
        self.result: str = ""
        self.error: str = ""
        self.span_id: str = ""

    def __enter__(self) -> "_ToolSpan":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_val is not None and not self.error:
            self.error = str(exc_val)
        self.span_id = self._emitter.tool_call(
            self._trace_id,
            self._parent_span_id,
            self._start_ns,
            tool_name=self._tool_name,
            input_kwargs=self._input_kwargs,
            result=self.result,
            error=self.error,
        )


# ── Attribute helpers ────────────────────────────────────────────────────────

def _str_attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


def _int_attr(key: str, value: int) -> dict:
    return {"key": key, "value": {"intValue": value}}


def _completion_event(text: str) -> dict:
    return {
        "name": "gen_ai.completion",
        "attributes": [_str_attr("gen_ai.completion", text[:500])],
    }

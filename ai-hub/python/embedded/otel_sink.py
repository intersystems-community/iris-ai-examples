"""
otel_sink — in-process OTLP/HTTP sink for demos and tests.

Starts a minimal HTTP server on a free port in a background daemon thread.
Receives OTLP/HTTP JSON payloads and stores spans in memory.
Provides pretty_print() to render a coloured span tree to stdout.

Usage (demo):

    from otel_sink import OTelSink
    sink = OTelSink()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = sink.endpoint
    # ... run demo ...
    sink.pretty_print()

Usage (pytest fixture):

    @pytest.fixture
    def otel_sink():
        sink = OTelSink()
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = sink.endpoint
        yield sink
        del os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
        sink.stop()
        sink.pretty_print()

Pure stdlib. No opentelemetry package required.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


# ── Span record ───────────────────────────────────────────────────────────────

@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str
    start_ns: int
    end_ns: int
    status_code: int            # 0=UNSET, 1=OK, 2=ERROR
    attributes: dict[str, Any]
    events: list[dict]

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000

    @property
    def status_label(self) -> str:
        return {0: "UNSET", 1: "OK", 2: "ERROR"}.get(self.status_code, "?")


# ── Sink ──────────────────────────────────────────────────────────────────────

class OTelSink:
    """In-process OTLP/HTTP receiver. Thread-safe span store + pretty printer."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._spans: list[Span] = []
        self._lock = threading.Lock()

        sink_self = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self_h):
                try:
                    length = int(self_h.headers.get("Content-Length", 0))
                    body = self_h.rfile.read(length)
                    sink_self._ingest(json.loads(body))
                except Exception:
                    pass
                self_h.send_response(200)
                self_h.end_headers()

            def log_message(self_h, fmt, *args):  # silence access log
                pass

        self._server = HTTPServer((host, port), _Handler)
        actual_port = self._server.server_address[1]
        self.endpoint = f"http://{host}:{actual_port}"

        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()

    @property
    def spans(self) -> list[Span]:
        with self._lock:
            return list(self._spans)

    def spans_for_trace(self, trace_id: str) -> list[Span]:
        with self._lock:
            return [s for s in self._spans if s.trace_id == trace_id]

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def _ingest(self, payload: dict) -> None:
        for rs in payload.get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                for s in ss.get("spans", []):
                    attrs: dict[str, Any] = {}
                    for a in s.get("attributes", []):
                        v = a.get("value", {})
                        attrs[a["key"]] = (
                            v.get("stringValue")
                            or v.get("intValue")
                            or v.get("boolValue")
                        )
                    span = Span(
                        name=s.get("name", ""),
                        trace_id=s.get("traceId", ""),
                        span_id=s.get("spanId", ""),
                        parent_span_id=s.get("parentSpanId", ""),
                        start_ns=int(s.get("startTimeUnixNano", 0)),
                        end_ns=int(s.get("endTimeUnixNano", 0)),
                        status_code=s.get("status", {}).get("code", 0),
                        attributes=attrs,
                        events=s.get("events", []),
                    )
                    with self._lock:
                        self._spans.append(span)

    # ── Pretty printer ────────────────────────────────────────────────────────

    def pretty_print(
        self,
        *,
        show_attrs: bool = True,
        show_events: bool = True,
        file=None,
    ) -> None:
        """Print a span tree grouped by trace to stdout (or file)."""
        import sys as _sys
        out = file or _sys.stdout

        spans = self.spans
        if not spans:
            print("  (no spans captured)", file=out)
            return

        # Group by trace
        traces: dict[str, list[Span]] = {}
        for s in spans:
            traces.setdefault(s.trace_id, []).append(s)

        for trace_id, trace_spans in traces.items():
            print(f"\nTrace {trace_id}", file=out)
            _print_tree(trace_spans, show_attrs=show_attrs,
                        show_events=show_events, file=out)


# ── Tree renderer ─────────────────────────────────────────────────────────────

_STATUS_COLOUR = {0: "", 1: "\033[32m", 2: "\033[31m"}   # green / red
_RESET = "\033[0m"
_DIM   = "\033[2m"


def _print_tree(
    spans: list[Span],
    *,
    show_attrs: bool,
    show_events: bool,
    file,
) -> None:
    by_id = {s.span_id: s for s in spans}
    children: dict[str, list[Span]] = {s.span_id: [] for s in spans}
    roots: list[Span] = []

    for s in sorted(spans, key=lambda x: x.start_ns):
        pid = s.parent_span_id
        if pid and pid in children:
            children[pid].append(s)
        else:
            roots.append(s)

    def _render(s: Span, indent: int) -> None:
        prefix = "  " * indent
        colour = _STATUS_COLOUR.get(s.status_code, "")
        dur = f"{s.duration_ms:.1f}ms"
        status = f"[{s.status_label}]" if s.status_code != 0 else ""
        sid_short = s.span_id[:8]
        print(
            f"{prefix}{colour}{s.name}{_RESET}"
            f"  {_DIM}{dur}  {sid_short}{_RESET}"
            + (f"  {colour}{status}{_RESET}" if status else ""),
            file=file,
        )

        if show_attrs:
            _SHOW_KEYS = {
                "gen_ai.tool.input", "gen_ai.tool.output", "gen_ai.tool.error",
                "gen_ai.request.model", "gen_ai.usage.input_tokens",
                "gen_ai.usage.output_tokens", "gen_ai.tool.denied",
                "gen_ai.system", "gen_ai.tool.call_id", "session.id",
            }
            for k, v in s.attributes.items():
                if k not in _SHOW_KEYS:
                    continue
                val = str(v)
                if len(val) > 120:
                    val = val[:117] + "..."
                print(f"{prefix}  {_DIM}{k}: {val}{_RESET}", file=file)

        if show_events:
            for ev in s.events:
                ev_attrs = {
                    a["key"]: (a.get("value", {}).get("stringValue", ""))
                    for a in ev.get("attributes", [])
                }
                print(
                    f"{prefix}  {_DIM}event:{ev.get('name','')} "
                    f"{json.dumps(ev_attrs)[:100]}{_RESET}",
                    file=file,
                )

        for child in sorted(children.get(s.span_id, []), key=lambda x: x.start_ns):
            _render(child, indent + 1)

    for root in roots:
        _render(root, 1)

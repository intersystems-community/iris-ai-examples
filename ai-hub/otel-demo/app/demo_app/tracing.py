"""OTel plumbing for the demo app.

iris_llm uses the OTel API only, so this process owns the SDK: one
TracerProvider, one OTLP/HTTP exporter aimed at the collector. The standard
OTEL_* environment variables configure the exporter.
"""

from typing import Dict

from opentelemetry import trace


def init_tracing(service_name: str) -> None:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)


def current_traceparent() -> str:
    """W3C traceparent of the active span, or "" when nothing is recording."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return ""
    # Only the sampled bit: the SDK also sets the level-2 random-trace-id bit
    # (flags 03), which older traceparent parsers on the IRIS side may reject.
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{int(ctx.trace_flags) & 1:02x}"


def trace_url(langfuse_url: str, project_id: str, trace_id: int) -> str:
    return f"{langfuse_url.rstrip('/')}/project/{project_id}/traces/{trace_id:032x}"


def session_attributes(session_id: str) -> Dict[str, str]:
    """Langfuse groups by langfuse.session.id; semconv and iris_llm use the other two."""
    return {
        "session.id": session_id,
        "langfuse.session.id": session_id,
        "gen_ai.conversation.id": session_id,
    }

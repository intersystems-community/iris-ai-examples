"""The two values every reply needs: a traceparent for IRIS and a Langfuse link."""

import re

from demo_app import tracing


def test_traceparent_is_the_w3c_form_of_the_current_span(tracer, spans):
    with tracer.start_as_current_span("turn") as span:
        tp = tracing.current_traceparent()
        ctx = span.get_span_context()
    assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-01", tp)
    assert tp == f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01"


def test_no_span_means_no_traceparent():
    assert tracing.current_traceparent() == ""


def test_trace_url_points_at_the_project_trace_page():
    url = tracing.trace_url("http://lf.example:3300/", "demo", 0xABC)
    assert url == "http://lf.example:3300/project/demo/traces/" + f"{0xABC:032x}"


def test_session_attributes_carry_both_spellings():
    attrs = tracing.session_attributes("s-1")
    assert attrs["session.id"] == "s-1"
    assert attrs["langfuse.session.id"] == "s-1"
    assert attrs["gen_ai.conversation.id"] == "s-1"

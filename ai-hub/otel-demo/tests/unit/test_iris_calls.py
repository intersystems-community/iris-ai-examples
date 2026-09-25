"""Both tabs reach IRIS through the native API and hand it the current span."""

import json

from demo_app import iris_calls


class FakeNative:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def classMethodValue(self, cls, method, *args):
        self.calls.append((cls, method, args))
        return self.result


def test_ask_agent_passes_session_question_and_traceparent(tracer, spans):
    native = FakeNative(json.dumps({"content": "hello", "error": ""}))
    with tracer.start_as_current_span("turn") as span:
        reply = iris_calls.ask_agent(native, "s-1", "hi")
        want_tp = f"00-{span.get_span_context().trace_id:032x}-"
    ((cls, method, (sid, question, tp)),) = native.calls
    assert (cls, method) == ("Demo.AIHub.Chat", "Ask")
    assert (sid, question) == ("s-1", "hi")
    assert tp.startswith(want_tp)
    assert reply == "hello"


def test_ask_agent_raises_the_objectscript_error():
    native = FakeNative(json.dumps({"content": "", "error": "ERROR #5002"}))
    try:
        iris_calls.ask_agent(native, "s", "q")
    except iris_calls.IrisCallError as exc:
        assert "5002" in str(exc)
    else:
        raise AssertionError("expected IrisCallError")


def test_lookup_patient_passes_the_traceparent(tracer, spans):
    native = FakeNative("Patient 42: Jane Doe")
    with tracer.start_as_current_span("execute_tool lookup_patient") as span:
        out = iris_calls.lookup_patient(native, "42")
        want = f"{span.get_span_context().span_id:016x}"
    ((cls, method, (pid, tp)),) = native.calls
    assert (cls, method) == ("Demo.AIHub.Chat", "Lookup")
    assert pid == "42" and tp.split("-")[2] == want
    assert out == "Patient 42: Jane Doe"

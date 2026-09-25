"""The LangChain tab owns its agent loop, so it owns invoke_agent and execute_tool.

ChatIris emits the chat spans itself; the loop here must put them, and the IRIS
call each tool makes, under one invoke_agent span per turn.
"""

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from demo_app import langchain_turn, tracing


class ScriptedModel:
    """Stands in for ChatIris.bind_tools(...): replays AIMessages in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def make_tool(calls):
    @tool
    def lookup_patient(patient_id: str) -> str:
        """Look up a patient's clinical summary by patient ID."""
        calls.append((patient_id, tracing.current_traceparent()))
        return f"summary for {patient_id}"

    return lookup_patient


def test_one_turn_nests_tools_under_invoke_agent(tracer, spans):
    calls = []
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "lookup_patient", "args": {"patient_id": "42"}}],
            ),
            AIMessage(content="Jane is stable."),
        ]
    )
    with tracer.start_as_current_span("turn"):
        answer = langchain_turn.run_turn(
            model, [make_tool(calls)], "How is 42?", history=[], session_id="s-9"
        )

    assert answer == "Jane is stable."
    finished = {s.name: s for s in spans.get_finished_spans()}
    agent = finished["invoke_agent iris-langchain"]
    tool_span = finished["execute_tool lookup_patient"]
    assert agent.parent.span_id == finished["turn"].context.span_id
    assert tool_span.parent.span_id == agent.context.span_id
    assert agent.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert agent.attributes["session.id"] == "s-9"
    assert tool_span.attributes["gen_ai.tool.name"] == "lookup_patient"
    assert tool_span.attributes["gen_ai.tool.call.id"] == "c1"

    # The tool body ran inside execute_tool, so the traceparent it would hand
    # to IRIS names that span.
    ((pid, tp),) = calls
    assert pid == "42"
    assert tp.split("-")[2] == f"{tool_span.context.span_id:016x}"

    # The second model call saw the tool result.
    assert model.seen[1][-1].content == "summary for 42"


def test_history_is_replayed_and_extended(tracer, spans):
    model = ScriptedModel([AIMessage(content="second answer")])
    history = []
    langchain_turn.run_turn(model, [], "q1", history=history, session_id="s")
    model.replies.append(AIMessage(content="third"))
    langchain_turn.run_turn(model, [], "q2", history=history, session_id="s")
    assert [m.content for m in model.seen[1]][-3:] == ["q1", "second answer", "q2"]


def test_a_tool_error_is_returned_to_the_model_and_marks_the_span(tracer, spans):
    @tool
    def broken(x: str) -> str:
        """Always fails."""
        raise RuntimeError("boom")

    model = ScriptedModel(
        [
            AIMessage(content="", tool_calls=[{"id": "c", "name": "broken", "args": {"x": "1"}}]),
            AIMessage(content="sorry"),
        ]
    )
    assert langchain_turn.run_turn(model, [broken], "q", history=[], session_id="s") == "sorry"
    span = {s.name: s for s in spans.get_finished_spans()}["execute_tool broken"]
    assert span.attributes["error.type"] == "RuntimeError"
    assert "boom" in model.seen[1][-1].content


def test_the_loop_stops_after_max_steps(tracer, spans):
    looping = AIMessage(content="", tool_calls=[{"id": "c", "name": "t", "args": {}}])

    @tool
    def t() -> str:
        """No-op."""
        return "ok"

    model = ScriptedModel([looping] * 10)
    answer = langchain_turn.run_turn(model, [t], "q", history=[], session_id="s", max_steps=3)
    assert "step limit" in answer

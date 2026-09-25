"""The LangChain tab's agent loop.

ChatIris is a leaf: it emits one `chat` span per model call and never a turn
span. Whoever owns the loop owns `invoke_agent` and `execute_tool`, and here
that is this module, so the span tree matches the one the Rust %AI.Agent loop
emits on the other tab.
"""

from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from demo_app.tracing import session_attributes

AGENT_NAME = "iris-langchain"
_tracer = trace.get_tracer("demo_app.langchain_turn")


def run_turn(
    model,
    tools,
    question: str,
    history: List[BaseMessage],
    session_id: str,
    max_steps: int = 6,
) -> str:
    """Answer one question, calling tools as the model asks. Extends history in place."""
    by_name = {t.name: t for t in tools}
    bound = model.bind_tools(tools) if tools else model
    messages = history + [HumanMessage(content=question)]

    with _tracer.start_as_current_span(
        f"invoke_agent {AGENT_NAME}",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": AGENT_NAME,
            **session_attributes(session_id),
        },
    ) as agent_span:
        answer = None
        for _ in range(max_steps):
            reply: AIMessage = bound.invoke(messages)
            messages.append(reply)
            if not reply.tool_calls:
                answer = reply.content
                break
            for call in reply.tool_calls:
                messages.append(_execute_tool(by_name, call))
        if answer is None:
            answer = f"(stopped: step limit of {max_steps} reached)"
            agent_span.set_status(Status(StatusCode.ERROR, "step limit"))

    history[:] = messages
    return answer


def _execute_tool(by_name, call) -> ToolMessage:
    name = call["name"]
    with _tracer.start_as_current_span(
        f"execute_tool {name}",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": name,
            "gen_ai.tool.call.id": call.get("id", ""),
        },
    ) as span:
        try:
            tool = by_name[name]
            result = str(tool.invoke(call.get("args", {})))
        except Exception as exc:  # the model gets the error and may recover
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            result = f"error: {exc}"
    return ToolMessage(content=result, tool_call_id=call.get("id", ""))

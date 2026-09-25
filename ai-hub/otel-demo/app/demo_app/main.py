"""Wires the real backends: IRIS over the native API, OpenAI through iris_llm.

    uvicorn demo_app.main:app --host 0.0.0.0 --port 8000
"""

import os

from demo_app import iris_calls, langchain_turn, llm_config, tracing, web
from demo_app.iris_session import IrisSession

tracing.init_tracing(os.environ.get("OTEL_SERVICE_NAME", "otel-demo-app"))

import iris  # noqa: E402  intersystems-irispython
from iris_llm import Provider  # noqa: E402
from iris_llm.langchain import ChatIris  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

SYSTEM = (
    "You are a clinical assistant. Use the lookup_patient tool for any question "
    "about a patient. Answer in two sentences or fewer."
)


def connect_iris():
    conn = iris.connect(
        os.environ.get("IRIS_HOST", "iris"),
        int(os.environ.get("IRIS_SUPERSERVER_PORT", "1972")),
        os.environ.get("IRIS_NAMESPACE", "USER"),
        os.environ.get("IRIS_USERNAME", "_SYSTEM"),
        os.environ.get("IRIS_PASSWORD", "SYS"),
    )
    return iris.createIRIS(conn)


class Backends:
    def __init__(self):
        # Separate connections: Demo.AIHub.Chat.Ask keeps %AI.Agent sessions in
        # its process, and a LangChain tool call must not queue behind a turn.
        self.agent_iris = IrisSession(connect_iris)
        self.tool_iris = IrisSession(connect_iris)
        model, settings = llm_config.from_env(os.environ)
        self.model = ChatIris(provider=Provider("openai", settings), model=model)
        self.histories = {}

        tool_iris = self.tool_iris

        @tool
        def lookup_patient(patient_id: str) -> str:
            """Look up a patient's clinical summary by patient ID."""
            return tool_iris.call(iris_calls.lookup_patient, patient_id)

        self.tools = [lookup_patient]

    def ai_agent(self, session_id, question):
        return self.agent_iris.call(iris_calls.ask_agent, session_id, question)

    def langchain(self, session_id, question):
        from langchain_core.messages import SystemMessage

        from iris_llm.telemetry import set_session

        history = self.histories.setdefault(session_id, [SystemMessage(content=SYSTEM)])
        # Baggage, so ChatIris stamps session.id on its own chat spans.
        with set_session(session_id):
            return langchain_turn.run_turn(
                self.model, self.tools, question, history=history, session_id=session_id
            )


app = web.create_app(
    backends=Backends(),
    langfuse_url=os.environ.get("LANGFUSE_PUBLIC_URL", "http://localhost:3300"),
    project_id=os.environ.get("LANGFUSE_INIT_PROJECT_ID", "otel-demo"),
)

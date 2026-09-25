"""User story: a question on either tab shows up in Langfuse as one connected trace.

Runs against the live stack. Set, from the stack's .env:

    DEMO_APP_URL          e.g. http://localhost:8095
    LANGFUSE_URL          e.g. http://localhost:3300
    LANGFUSE_INIT_PROJECT_PUBLIC_KEY / LANGFUSE_INIT_PROJECT_SECRET_KEY

The trace link in each reply is the contract: the test follows it to the trace
id and reads that trace's observations back through the Langfuse public API.
"""

import os
import re
import time

import httpx
import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("DEMO_APP_URL"), reason="DEMO_APP_URL not set; stack not running"
    ),
]

APP = os.environ.get("DEMO_APP_URL", "")
LANGFUSE = os.environ.get("LANGFUSE_URL", "")
AUTH = (
    os.environ.get("LANGFUSE_INIT_PROJECT_PUBLIC_KEY", ""),
    os.environ.get("LANGFUSE_INIT_PROJECT_SECRET_KEY", ""),
)
QUESTION = "Use the patient lookup tool for patient 42, then give a one-sentence summary."


def ask(tab):
    r = httpx.post(f"{APP}/chat/{tab}", data={"question": QUESTION}, timeout=120)
    r.raise_for_status()
    m = re.search(r"/traces/([0-9a-f]{32})", r.text)
    assert m, f"no trace link in reply: {r.text[:400]}"
    assert "error" not in r.text.lower(), r.text[:400]
    return m.group(1)


def observations(trace_id, want, timeout=90):
    """Poll until every (type, name prefix) in `want` is present.

    Langfuse ingests asynchronously. v4 serves observations from
    /api/public/v2/observations; it types gen_ai spans (AGENT, GENERATION, TOOL)
    and names a TOOL observation after the tool itself.
    """
    deadline = time.time() + timeout
    obs = []
    while time.time() < deadline:
        r = httpx.get(
            f"{LANGFUSE}/api/public/v2/observations",
            params={"traceId": trace_id, "limit": 100, "fields": "core,basic,usage"},
            auth=AUTH,
            timeout=30,
        )
        if r.status_code == 200:
            obs = r.json()["data"]
            if all(any(o["type"] == t and o["name"].startswith(n) for o in obs) for t, n in want):
                return obs
        time.sleep(3)
    got = sorted((o["type"], o["name"]) for o in obs)
    raise AssertionError(f"trace {trace_id} has {got}, wanted {want}")


def assert_one_session(obs):
    sessions = {o["sessionId"] for o in obs if o.get("sessionId")}
    assert len(sessions) == 1, f"trace not grouped into one Langfuse session: {sessions}"


def test_ai_agent_tab_trace_spans_app_rust_and_interop():
    obs = observations(
        ask("ai-agent"),
        [
            ("SPAN", "chat turn"),
            ("AGENT", "invoke_agent %AI.Agent"),
            ("GENERATION", "chat "),
            ("TOOL", "LookupPatient"),
            ("SPAN", "bs."),
            ("SPAN", "bp."),
            ("SPAN", "bo."),
        ],
    )
    assert_one_session(obs)


def test_langchain_tab_trace_spans_python_and_interop():
    obs = observations(
        ask("langchain"),
        [
            ("SPAN", "chat turn"),
            ("AGENT", "invoke_agent iris-langchain"),
            ("GENERATION", "chat "),
            ("TOOL", "lookup_patient"),
            ("SPAN", "bs."),
            ("SPAN", "bo."),
        ],
    )
    assert_one_session(obs)
    assert any(
        o["type"] == "GENERATION" and o.get("totalUsage") for o in obs
    ), "no chat observation carries token usage"

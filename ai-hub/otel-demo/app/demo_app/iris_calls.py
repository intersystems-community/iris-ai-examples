"""The two IRIS entry points, called over the native API.

Each call hands IRIS the active span's traceparent, so the spans IRIS emits
(the Rust agent loop and the interop production) join this process's trace.
"""

import json

from demo_app.tracing import current_traceparent

CHAT_CLASS = "Demo.AIHub.Chat"


class IrisCallError(RuntimeError):
    pass


def ask_agent(native, session_id: str, question: str) -> str:
    """One %AI.Agent turn. Demo.AIHub.Chat.Ask keeps the session per session_id."""
    raw = native.classMethodValue(CHAT_CLASS, "Ask", session_id, question, current_traceparent())
    reply = json.loads(raw)
    if reply.get("error"):
        raise IrisCallError(reply["error"])
    return reply.get("content", "")


def lookup_patient(native, patient_id: str) -> str:
    """Run the interop production's patient lookup (BS -> BP -> BO)."""
    return native.classMethodValue(CHAT_CLASS, "Lookup", patient_id, current_traceparent())

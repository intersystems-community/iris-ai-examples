"""One FastAPI app, two tabs. Every reply is an HTMX fragment with its trace link."""

import html
import uuid

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from demo_app.tracing import session_attributes, trace_url

TABS = {
    "ai-agent": ("%AI.Agent", "ObjectScript %AI.Agent; the agent loop runs in Rust inside IRIS"),
    "langchain": ("iris_llm + LangChain", "Python LangChain loop over iris_llm ChatIris"),
}
COOKIE = "otel_demo_sid"

_tracer = trace.get_tracer("demo_app.web")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>AI Hub observability demo</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 920px; margin: 2em auto; }}
.tabs button {{ padding: .5em 1em; }} .tabs button.on {{ font-weight: bold; }}
.pane {{ display: none; }} .pane.on {{ display: block; }}
.turn {{ border-left: 3px solid #88a; padding: .3em .8em; margin: .8em 0; white-space: pre-wrap; }}
.q {{ color: #555; }} .err {{ color: #a22; }} .trace {{ font-size: .85em; }}
input[name=question] {{ width: 75%; padding: .4em; }}
</style></head>
<body>
<h2>AI Hub observability demo</h2>
<p>Both tabs export OTel spans to <a href="{langfuse}" target="_blank">Langfuse</a>.
Each reply links to its trace.</p>
<div class="tabs">{buttons}</div>
{panes}
<script>
function show(t) {{
  document.querySelectorAll('.pane,.tabs button').forEach(e => e.classList.remove('on'));
  document.getElementById('pane-' + t).classList.add('on');
  document.getElementById('btn-' + t).classList.add('on');
}}
show('ai-agent');
</script>
</body></html>"""

PANE = """<div class="pane" id="pane-{tab}">
<p><i>{blurb}</i></p>
<div id="log-{tab}"></div>
<form hx-post="/chat/{tab}" hx-target="#log-{tab}" hx-swap="beforeend"
      hx-on::after-request="this.reset()">
<input name="question" placeholder="Ask about patient 42, 7 or 13" autocomplete="off">
<button>Send</button> <span class="htmx-indicator">thinking...</span>
</form></div>"""


def create_app(backends, langfuse_url: str, project_id: str) -> FastAPI:
    """backends has ai_agent(session_id, question) and langchain(session_id, question)."""
    app = FastAPI()
    handlers = {"ai-agent": backends.ai_agent, "langchain": backends.langchain}

    @app.get("/", response_class=HTMLResponse)
    def index():
        buttons = "".join(
            f'<button id="btn-{t}" onclick="show(\'{t}\')">{html.escape(label)}</button>'
            for t, (label, _) in TABS.items()
        )
        panes = "".join(
            PANE.format(tab=t, blurb=html.escape(blurb)) for t, (_, blurb) in TABS.items()
        )
        return PAGE.format(langfuse=html.escape(langfuse_url), buttons=buttons, panes=panes)

    @app.post("/chat/{tab}", response_class=HTMLResponse)
    def chat(tab: str, request: Request, question: str = Form(...)):
        if tab not in handlers:
            return HTMLResponse("unknown tab", status_code=404)
        base = request.cookies.get(COOKIE) or uuid.uuid4().hex[:12]
        session_id = f"{base}-{tab}"
        label = TABS[tab][0]
        with _tracer.start_as_current_span(
            f"chat turn ({label})",
            kind=trace.SpanKind.SERVER,
            attributes={
                **session_attributes(session_id),
                "langfuse.trace.name": f"chat turn ({label})",
                "langfuse.trace.input": question,
                "demo.tab": tab,
            },
        ) as span:
            try:
                answer = handlers[tab](session_id, question)
                span.set_attribute("langfuse.trace.output", answer)
                body, css = answer, ""
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                body, css = f"error: {exc}", "err"
            link = trace_url(langfuse_url, project_id, span.get_span_context().trace_id)
        fragment = (
            f'<div class="turn"><div class="q">&gt; {html.escape(question)}</div>'
            f'<div class="{css}">{html.escape(str(body))}</div>'
            f'<div class="trace"><a href="{html.escape(link)}" target="_blank">'
            f"trace in Langfuse</a></div></div>"
        )
        resp = HTMLResponse(fragment)
        resp.set_cookie(COOKIE, base, max_age=86400)
        return resp

    return app

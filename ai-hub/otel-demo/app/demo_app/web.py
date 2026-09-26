"""One FastAPI app, two tabs. Every reply is an HTMX fragment with its trace link."""

import html
import json
import uuid
from pathlib import Path

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
#about {{ background: #f4f5fa; border: 1px solid #dde; padding: .4em 1em; margin: 1em 0; }}
#about pre {{ font-size: .85em; margin: .4em 0; }}
</style></head>
<body>
<h2>AI Hub observability demo</h2>
<p>Both tabs export OTel spans to <a href="{langfuse}" target="_blank">Langfuse</a>.
Each reply links to its trace.</p>
{login}<details id="about" open><summary><b>What you are looking at</b></summary>
<p>Each tab answers questions about a patient by calling one tool, and the tool runs
through an IRIS interoperability production. Ask a question, then open
<i>trace in Langfuse</i> under the reply. The whole turn is <b>one trace</b>:</p>
<pre>chat turn                  FastAPI app, where the trace starts
└─ invoke_agent            the agent loop, in Rust inside IRIS (%AI.Agent tab)
   ├─ chat &lt;model&gt;         each model call, with token usage
   ├─ execute_tool         the tool call, e.g. LookupPatient
   │  └─ bs.ToolService    business service
   │     └─ bp.LookupBP    business process
   │        └─ bo.LookupBO business operation
   └─ chat &lt;model&gt;         the answer</pre>
<p>The LangChain tab builds the same tree from Python, with its agent and tool spans
emitted by the app instead of the Rust core.</p>
<p>What makes it one trace is two AI Hub hooks: <code>%AI.System.Configure("telemetry:context")</code>
hands the app's trace context to the Rust core, and <code>%AI.Tool.CurrentTraceparent()</code>
hands the tool's span to the production. This stack runs a patched AI Hub build that has
both. A stock build does not, and there the app, the agent and the production each start
their own trace.</p>
<p>Three processes export those spans: the app (Python OTel SDK), the Rust core in IRIS
(<code>invoke_agent</code>, <code>chat</code>, <code>execute_tool</code>) and the production
(<code>%Trace</code>). All three send OTLP to one OTel Collector, and only the collector
talks to Langfuse. No MCP server is in this path: the agent runs in-process through
<code>%AI.Agent</code>.</p>
<p><a href="/architecture" target="_blank">Architecture diagram: the app, the OTel hooks and the patch</a></p>
{patch}</details>
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


def login_from_env(env) -> tuple[str, str] | None:
    """The Langfuse login to print on the page, or None. Off unless the host sets
    LANGFUSE_SHOW_LOGIN=1: only an internal demo host should publish its password."""
    email = env.get("LANGFUSE_INIT_USER_EMAIL", "")
    password = env.get("LANGFUSE_INIT_USER_PASSWORD", "")
    if env.get("LANGFUSE_SHOW_LOGIN") != "1" or not email or not password:
        return None
    return email, password


def patch_links_from_env(env) -> list[tuple[str, str]]:
    """(label, url) pairs for the patch behind this build, from DEMO_PATCH_LINKS as a JSON
    list of pairs. The ai-core MRs are on an internal GitLab, so the host supplies the URLs
    and the source carries none. Anything that is not an http(s) pair is dropped."""
    try:
        pairs = json.loads(env.get("DEMO_PATCH_LINKS") or "[]")
    except ValueError:
        return []
    return [(str(label), str(url)) for label, url in (p for p in pairs if isinstance(p, list) and len(p) == 2)
            if str(url).startswith(("https://", "http://"))]


ARCHITECTURE = Path(__file__).parent / "static" / "architecture.html"


def create_app(backends, langfuse_url: str, project_id: str,
               langfuse_login: tuple[str, str] | None = None,
               patch_links: list[tuple[str, str]] | None = None) -> FastAPI:
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
        login = ""
        if langfuse_login:
            email, password = (html.escape(x) for x in langfuse_login)
            login = f'<p class="trace">Langfuse login: <code>{email}</code> / <code>{password}</code></p>\n'
        patch = ""
        if patch_links:
            items = "".join(f'<li><a href="{html.escape(url)}" target="_blank">{html.escape(label)}</a></li>'
                            for label, url in patch_links)
            patch = f"<p>The patch behind this build:</p><ul>{items}</ul>\n"
        return PAGE.format(langfuse=html.escape(langfuse_url), login=login, patch=patch,
                           buttons=buttons, panes=panes)

    @app.get("/architecture", response_class=HTMLResponse)
    def architecture():
        return ARCHITECTURE.read_text()

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

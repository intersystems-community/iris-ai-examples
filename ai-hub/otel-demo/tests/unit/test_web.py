"""The HTMX surface: two tabs, one fragment per reply, each with its trace link."""

from fastapi.testclient import TestClient

from demo_app import web


class Backends:
    def __init__(self):
        self.agent_calls = []
        self.lc_calls = []

    def ai_agent(self, session_id, question):
        self.agent_calls.append((session_id, question))
        return "agent says hi"

    def langchain(self, session_id, question):
        self.lc_calls.append((session_id, question))
        return "chain says hi"


def client(backends):
    app = web.create_app(
        backends=backends, langfuse_url="http://lf.example:3300", project_id="demo"
    )
    return TestClient(app)


def test_index_shows_both_tabs():
    page = client(Backends()).get("/").text
    assert "%AI.Agent" in page and "LangChain" in page
    assert 'hx-post="/chat/ai-agent"' in page and 'hx-post="/chat/langchain"' in page


def test_each_reply_links_to_its_own_trace(spans):
    b = Backends()
    c = client(b)
    r1 = c.post("/chat/ai-agent", data={"question": "q1"})
    r2 = c.post("/chat/langchain", data={"question": "q2"})
    assert "agent says hi" in r1.text and "chain says hi" in r2.text
    roots = [s for s in spans.get_finished_spans() if s.parent is None]
    assert len(roots) == 2
    for resp, root in zip((r1, r2), roots):
        assert f"http://lf.example:3300/project/demo/traces/{root.context.trace_id:032x}" in resp.text


def test_the_session_cookie_is_stable_and_separate_per_tab(spans):
    b = Backends()
    c = client(b)
    c.post("/chat/ai-agent", data={"question": "a"})
    c.post("/chat/ai-agent", data={"question": "b"})
    c.post("/chat/langchain", data={"question": "c"})
    (s1, _), (s2, _) = b.agent_calls
    ((s3, _),) = b.lc_calls
    assert s1 == s2
    assert s3 != s1
    roots = [s for s in spans.get_finished_spans() if s.parent is None]
    assert {r.attributes["session.id"] for r in roots} == {s1, s3}


def test_a_backend_failure_renders_an_error_with_the_trace_link(spans):
    class Broken(Backends):
        def ai_agent(self, session_id, question):
            raise RuntimeError("iris down")

    r = client(Broken()).post("/chat/ai-agent", data={"question": "q"})
    assert r.status_code == 200
    assert "iris down" in r.text and "/traces/" in r.text
    (root,) = [s for s in spans.get_finished_spans() if s.parent is None]
    assert root.status.status_code.name == "ERROR"


def test_reply_text_is_escaped():
    class Evil(Backends):
        def langchain(self, session_id, question):
            return "<script>x</script>"

    r = client(Evil()).post("/chat/langchain", data={"question": "q"})
    assert "<script>x" not in r.text


def test_the_langfuse_login_is_shown_only_when_the_host_opts_in():
    on = {"LANGFUSE_SHOW_LOGIN": "1", "LANGFUSE_INIT_USER_EMAIL": "demo@example.com",
          "LANGFUSE_INIT_USER_PASSWORD": "pw<1>"}
    assert web.login_from_env(on) == ("demo@example.com", "pw<1>")
    assert web.login_from_env({**on, "LANGFUSE_SHOW_LOGIN": ""}) is None
    assert web.login_from_env({k: v for k, v in on.items() if k != "LANGFUSE_SHOW_LOGIN"}) is None
    assert web.login_from_env({**on, "LANGFUSE_INIT_USER_PASSWORD": ""}) is None


def test_the_index_prints_the_login_escaped_when_given_and_nothing_otherwise():
    app = web.create_app(backends=Backends(), langfuse_url="http://lf.example:3300",
                         project_id="demo", langfuse_login=("demo@example.com", "pw<1>"))
    page = TestClient(app).get("/").text
    assert "demo@example.com" in page and "pw&lt;1&gt;" in page and "pw<1>" not in page
    assert "demo@example.com" not in client(Backends()).get("/").text


def test_the_page_says_what_the_viewer_is_looking_at():
    page = client(Backends()).get("/").text
    about = page[page.index('id="about"'):]
    for layer in ("FastAPI", "Rust", "execute_tool", "business service", "business process",
                  "business operation", "one trace"):
        assert layer in about, layer
    assert "telemetry:context" in about and "CurrentTraceparent" in about
    assert "stock" in about  # says the build is patched, not a shipped release


def test_the_architecture_diagram_is_served_and_linked_from_the_blurb():
    c = client(Backends())
    about = c.get("/").text
    assert 'href="/architecture"' in about[about.index('id="about"'):]
    r = c.get("/architecture")
    assert r.status_code == 200 and "<svg" in r.text
    for part in ("%AI.Agent", "execute_tool", "bs.ToolService", "Langfuse", "7440647"):
        assert part in r.text, part


def test_patch_links_come_from_the_host_not_the_source():
    """The ai-core MRs live on an internal GitLab; the public repo carries no URL for them."""
    env = {"DEMO_PATCH_LINKS": '[["ai-core MR !2", "https://git.example/mr/2"], ["bad", "javascript:x"]]'}
    assert web.patch_links_from_env(env) == [("ai-core MR !2", "https://git.example/mr/2")]
    assert web.patch_links_from_env({}) == []
    assert web.patch_links_from_env({"DEMO_PATCH_LINKS": "not json"}) == []
    app = web.create_app(backends=Backends(), langfuse_url="http://lf.example:3300", project_id="demo",
                         patch_links=[("MR <2>", "https://git.example/mr/2")])
    page = TestClient(app).get("/").text
    assert 'href="https://git.example/mr/2"' in page and "MR &lt;2&gt;" in page
    assert "git.example" not in client(Backends()).get("/").text
    source = (web.Path(web.__file__).read_text())
    assert "iscinternal" not in source

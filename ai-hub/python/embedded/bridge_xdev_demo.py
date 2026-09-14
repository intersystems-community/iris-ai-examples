"""
bridge_xdev_demo — @tool decorator + xdev SQL + OTel, bridged to ObjectScript

Demonstrates the full embedded Python stack in one script:

  1. Define Python tools with @tool — each reads live IRIS data via iris.dbapi
     (xdev path: getEmbeddedConnection(), zero TCP overhead, in-process SQL).
  2. Register those tools as a compiled ObjectScript %AI.ToolSet via iris_tool_bridge.
  3. Run an iris_llm Agent that calls the tools to answer a question.
  4. Emit OTel spans (gen_ai.* semantic conventions) for every LLM call and
     every tool execution to an OTLP/HTTP endpoint.

Run from inside the container:
    docker exec -e OPENAI_API_KEY=sk-... aicore-iris-xdev \\
        /usr/irissys/bin/irispython /tmp/bridge_xdev_demo.py

Or from the IRIS terminal:
    Set sys = ##class(%SYS.Python).Import("sys")
    Do sys.path.insert(0, "/path/to/aicore/python/embedded")
    Set demo = ##class(%SYS.Python).Import("bridge_xdev_demo")
    Do demo.run()

What makes this novel:
  - Python @tool functions with live IRIS SQL (xdev, not TCP)
  - Bridge compiles those tools into ObjectScript %AI.Tool at runtime
  - OTel spans emitted from Python for every LLM call and tool execution
  - All three layers (Python, ObjectScript, IRIS SQL) in a single process
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from otel_spans import OTelEmitter

# ─────────────────────────────────────────────────────────────────────────────
# OTel emitter — reads OTEL_* env vars; service name defaults to demo name
# ─────────────────────────────────────────────────────────────────────────────

_emitter = OTelEmitter(
    service_name=os.environ.get("OTEL_SERVICE_NAME", "aicore-bridge-xdev-demo"),
)


# ─────────────────────────────────────────────────────────────────────────────
# xdev connection — module-level singleton, shared across tool calls
# ─────────────────────────────────────────────────────────────────────────────

_xdev_conn = None

def _get_conn():
    global _xdev_conn
    if _xdev_conn is None:
        import iris
        import iris.dbapi as dbapi
        _xdev_conn = dbapi.connect()  # xdev when embedded, TCP loopback otherwise
    return _xdev_conn


def _sql(query: str, params: list | None = None) -> list:
    conn = _get_conn()
    cur = conn.cursor()
    if params:
        cur.execute(query, params)
    else:
        cur.execute(query)
    return cur.fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# ToolSet: live IRIS data via xdev + OTel instrumentation
# ─────────────────────────────────────────────────────────────────────────────

# Trace context set by the agent loop so tool spans are children of the chat span
_trace_ctx: dict = {"trace_id": "", "chat_span_id": ""}


def _make_instrumented_toolset(otel_enabled: bool):
    """Return a ToolSet class whose tools emit OTel spans on each call."""
    from iris_llm import ToolSet, tool

    class IRISInfoTools(ToolSet):

        @tool
        def list_namespaces(self) -> str:
            """List all namespaces available in this IRIS instance."""
            t0 = _emitter.now_ns()
            try:
                rows = _sql("SELECT Nsp FROM %SYS.Namespace_List()")
                result = json.dumps([r[0] for r in rows])
            except Exception as e:
                result = json.dumps({"error": str(e)})
            if otel_enabled and _trace_ctx["trace_id"]:
                _emitter.tool_call(
                    _trace_ctx["trace_id"], _trace_ctx["chat_span_id"], t0,
                    tool_name="list_namespaces", input_kwargs={}, result=result,
                )
            return result

        @tool
        def count_classes(self, namespace: str) -> str:
            """Count compiled ObjectScript classes in the given IRIS namespace."""
            t0 = _emitter.now_ns()
            try:
                rows = _sql("SELECT COUNT(*) FROM %Dictionary.ClassDefinition")
                count = rows[0][0] if rows else 0
                result = json.dumps({"namespace": namespace, "class_count": count,
                                     "note": "count is for current namespace via xdev"})
            except Exception as e:
                result = json.dumps({"error": str(e)})
            if otel_enabled and _trace_ctx["trace_id"]:
                _emitter.tool_call(
                    _trace_ctx["trace_id"], _trace_ctx["chat_span_id"], t0,
                    tool_name="count_classes", input_kwargs={"namespace": namespace},
                    result=result,
                )
            return result

        @tool
        def get_iris_version(self) -> str:
            """Return the IRIS version string."""
            t0 = _emitter.now_ns()
            try:
                rows = _sql("SELECT $ZVersion")
                result = json.dumps({"version": rows[0][0] if rows else "unknown"})
            except Exception as e:
                result = json.dumps({"error": str(e)})
            if otel_enabled and _trace_ctx["trace_id"]:
                _emitter.tool_call(
                    _trace_ctx["trace_id"], _trace_ctx["chat_span_id"], t0,
                    tool_name="get_iris_version", input_kwargs={}, result=result,
                )
            return result

    return IRISInfoTools


# Module-level _bridge_classes registry: populated at import time so that
# _get_toolset() can find IRISInfoTools in a fresh process (ObjectScript terminal,
# IRIS restart) without needing register_toolset() to have been called first.
try:
    from iris_llm import ToolSet as _ToolSet  # noqa: F401 — guard import
    _bridge_classes: dict = {"IRISInfoTools": _make_instrumented_toolset(otel_enabled=False)}
except Exception:
    _bridge_classes = {}


# ─────────────────────────────────────────────────────────────────────────────
# Demo phases
# ─────────────────────────────────────────────────────────────────────────────

def run_python_agent(otel_enabled: bool = True) -> None:
    """Phase 1: Agent runs entirely in Python — tools use xdev SQL."""
    print("\n=== Phase 1: Python Agent with xdev SQL tools ===\n")

    from iris_llm import Agent, Provider
    from iris_llm.utils import get_api_key

    api_key, provider_name = get_api_key()
    if not api_key:
        print("Skipped: no API key (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
        return

    from iris_llm import get_default_model
    provider = Provider(provider_name, json.dumps({"api_key": api_key}))
    model = get_default_model(provider_name)
    agent = Agent.with_provider(model, provider)
    agent.system_prompt = (
        "You are an IRIS database assistant. Use tools to inspect this IRIS instance "
        "and answer questions with real data. Be concise."
    )

    IRISInfoTools = _make_instrumented_toolset(otel_enabled)
    agent.add_tool_set(IRISInfoTools())

    trace_id = OTelEmitter.new_trace()

    query = (
        "What version of IRIS is this? List the namespaces and tell me "
        "how many classes are compiled in the USER namespace."
    )
    print(f"Query: {query}\n")

    # Pre-generate chat_span_id so tool spans emitted during agent.run() can
    # reference it as their parent — the chat span itself is flushed after run().
    chat_span_id = OTelEmitter.new_span() if otel_enabled else ""

    t0 = _emitter.now_ns()
    _trace_ctx["trace_id"] = trace_id
    _trace_ctx["chat_span_id"] = chat_span_id

    result = agent.run_result(query)
    response = result.output

    t1 = _emitter.now_ns()
    print(f"Answer: {response}\n")

    if otel_enabled:
        usage = result.usage or {}
        # Emit the chat span now — tool spans already emitted with this span as parent.
        _emitter.chat(
            trace_id, t0,
            span_id=chat_span_id,
            model=model,
            end_ns=t1,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            completion_text=str(response)[:200],
        )
        print(f"OTel trace emitted → trace_id={trace_id}")

    _trace_ctx["trace_id"] = ""


def run_configstore_agent(config_name: str, toolset_cls_name: str | None) -> None:
    """Phase 1b: Same query, but provider resolved from ConfigStore — governed, no raw API key.

    Calls Sample.AI.Bridge.Agent.RunQueryWithStats() which:
      1. Calls %AI.Utils.SettingStore.RegisterDefaults() to prime @{config:...} resolution
      2. Verifies the ConfigStore entry exists (RBAC enforced inside SettingStore.Expand)
      3. Creates %AI.Provider from the resolved settings
      4. Loads the bridge ToolSet (if provided) and runs the query
    """
    print(f"\n=== Phase 1b: ConfigStore-governed agent ({config_name}) ===\n")

    try:
        import iris
    except ImportError:
        print("Skipped: iris module not available (not running inside irispython)")
        return

    query = (
        "What version of IRIS is this? List the namespaces and tell me "
        "how many classes are compiled in the USER namespace."
    )
    print(f"Query: {query}\n")

    toolset = toolset_cls_name or ""
    result = iris.cls("Sample.AI.Bridge.Agent").RunQueryWithStats(config_name, toolset, query)

    error = result._Get("error") if result else "no result"
    if error:
        print(f"Error: {error}")
        return

    print(f"Answer: {result._Get('content')}\n")
    print(f"Tokens — prompt: {result._Get('prompt_tokens')}, "
          f"completion: {result._Get('completion_tokens')}")


def run_bridge_registration() -> str | None:
    """Phase 2: Register IRISInfoTools as a compiled ObjectScript %AI.ToolSet."""
    print("\n=== Phase 2: Register tools via iris_tool_bridge ===\n")

    try:
        import iris  # only available inside IRIS process
    except ImportError:
        print("Skipped: iris module not available (not running inside irispython)")
        return None

    from iris_tool_bridge import register_toolset

    IRISInfoTools = _make_instrumented_toolset(otel_enabled=False)
    module_dir = str(Path(__file__).parent.resolve())

    print(f"Registering IRISInfoTools from {module_dir} ...", flush=True)
    toolset_cls_name = register_toolset(
        IRISInfoTools,
        module_path="bridge_xdev_demo",
        module_dir=module_dir,
    )
    print(f"Compiled: {toolset_cls_name}", flush=True)

    return toolset_cls_name


def run_os_agent(toolset_cls_name: str, otel_enabled: bool = True) -> None:
    """Phase 3: ObjectScript ClassMethod dispatch → Python _get_toolset → xdev SQL.

    Calls each generated ClassMethod via iris.cls() — the same path an ObjectScript
    agent or terminal would use — confirming the full round-trip:

        iris.cls("Tmp.Bridge.IRISInfoTools").GetIrisVersion()
          → generated ObjectScript method
            → ##class(%SYS.Python).Import("iris_tool_bridge")
              → _get_toolset("bridge_xdev_demo", "IRISInfoTools")   ← from _bridge_classes
                → IRISInfoTools().get_iris_version()
                  → xdev SQL: SELECT $ZVersion

    OTel tool_call spans are emitted for each dispatch so they appear in the tree.
    """
    print("\n=== Phase 3: ObjectScript ClassMethod → _get_toolset → xdev SQL ===\n")

    try:
        import iris
    except ImportError:
        print("Skipped: iris module not available")
        return

    tool_cls_name = toolset_cls_name.replace("ToolSet", "")
    trace_id = OTelEmitter.new_trace() if otel_enabled else ""
    chat_span_id = OTelEmitter.new_span() if otel_enabled else ""
    t_phase_start = _emitter.now_ns()
    _trace_ctx["trace_id"] = trace_id
    _trace_ctx["chat_span_id"] = chat_span_id

    try:
        cls = iris.cls(tool_cls_name)

        calls = [
            ("GetIrisVersion",  lambda: cls.GetIrisVersion(),   "get_iris_version",  {}),
            ("ListNamespaces",  lambda: cls.ListNamespaces(),   "list_namespaces",   {}),
            ("CountClasses",    lambda: cls.CountClasses("USER"), "count_classes",   {"namespace": "USER"}),
        ]
        for label, fn, span_name, kwargs in calls:
            t0 = _emitter.now_ns()
            result_obj = fn()
            t1 = _emitter.now_ns()
            # DynamicObject — extract JSON via toJson()
            try:
                result_str = result_obj.toJson()
            except Exception:
                result_str = str(result_obj)
            print(f"{label:16s} → {result_str[:100]}", flush=True)
            if otel_enabled:
                _emitter.tool_call(
                    trace_id, chat_span_id, t0,
                    tool_name=span_name, input_kwargs=kwargs,
                    result=result_str, end_ns=t1,
                )

        print("\nAll ClassMethod dispatches succeeded.")
        if otel_enabled:
            _emitter.chat(trace_id, t_phase_start,
                          span_id=chat_span_id, end_ns=_emitter.now_ns())
            print(f"OTel trace emitted → trace_id={trace_id}")

    except Exception as e:
        print(f"Bridge dispatch error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _trace_ctx["trace_id"] = ""


def run(show_spans: bool = False, config_name: str = "") -> None:
    """Entry point — runs all three phases.

    show_spans:  start an in-process OTel sink and pretty-print the span tree
                 after each phase. Overrides OTEL_EXPORTER_OTLP_ENDPOINT.
    config_name: if set, run Phase 1b using this ConfigStore AI.LLM entry name
                 (e.g. "AI.LLM.SampleOpenAI") instead of a raw env-var API key.
    """
    sink = None
    if show_spans:
        from otel_sink import OTelSink
        sink = OTelSink()
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = sink.endpoint
        # Re-init the module-level emitter so it picks up the new endpoint
        global _emitter
        _emitter = OTelEmitter(
            service_name=os.environ.get("OTEL_SERVICE_NAME", "aicore-bridge-xdev-demo"),
        )
        print(f"OTel sink listening on {sink.endpoint}")

    otel_enabled = bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))
    if otel_enabled and not show_spans:
        print(f"OTel enabled → {os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')}")
    elif not otel_enabled:
        print("OTel disabled (set OTEL_EXPORTER_OTLP_ENDPOINT to enable)")

    # Phase 1: pure Python agent with xdev tools
    run_python_agent(otel_enabled=otel_enabled)
    if sink:
        print("\n--- Span tree (Phase 1) ---")
        sink.pretty_print()
        sink.clear()

    # Phase 2: compile tools into ObjectScript via bridge
    toolset_cls_name = run_bridge_registration()

    # Phase 1b: ConfigStore-governed agent (only when --config-name provided)
    if config_name:
        run_configstore_agent(config_name, toolset_cls_name)

    # Phase 3: agent using the ObjectScript ToolSet (requires Phase 2 success)
    if toolset_cls_name:
        run_os_agent(toolset_cls_name, otel_enabled=otel_enabled)
        if sink:
            print("\n--- Span tree (Phase 3) ---")
            sink.pretty_print()
    else:
        print("\nPhase 3 skipped (bridge registration not available outside irispython)")

    if sink:
        sink.stop()


if __name__ == "__main__":
    # irispython can buffer stdout; force line-buffering so output isn't eaten
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    import argparse
    parser = argparse.ArgumentParser(description="bridge_xdev_demo")
    parser.add_argument(
        "--show-spans", action="store_true",
        help="Start in-process OTel sink and pretty-print span tree after each phase",
    )
    parser.add_argument(
        "--config-name", default="",
        help="ConfigStore AI.LLM entry FQN (e.g. AI.LLM.SampleOpenAI) — "
             "enables Phase 1b: governed provider via IRIS RBAC instead of raw env key",
    )
    args = parser.parse_args()
    run(show_spans=args.show_spans, config_name=args.config_name)

"""Writes docs/sequence-*.sequence.json. Messages are listed in order and spaced evenly,
so adding one never means renumbering y by hand. Deliver each with archify, into app/demo_app/static/."""

import json
from pathlib import Path

DOCS = Path(__file__).parent
STEP = 42


def build(key, title, subtitle, width, participants, rows, segments, views, cards):
    msgs, y, seg_out = [], 184, []
    marks = {}
    for r in rows:
        if isinstance(r, str):          # segment marker
            marks[r] = y - 22
            continue
        f, t, label, *v = r
        m = {"from": f, "to": t, "y": y, "label": label}
        if v:
            m["variant"] = v[0]
        msgs.append(m)
        y += STEP
    names = list(marks)
    for i, n in enumerate(names):
        end = (marks[names[i + 1]] - 6) if i + 1 < len(names) else y - STEP + 20
        seg_out.append({"from": marks[n], "to": end, "label": n})
    spec = {
        "schema_version": 1, "diagram_type": "sequence",
        "meta": {"title": title, "subtitle": subtitle, "viewBox": [width, y + 60],
                 "animation": "trace", "visual_preset": "signal-flow", "quality_profile": "showcase",
                 "views": views},
        "participants": [dict(zip(("id", "type", "label", "sublabel"), p)) for p in participants],
        "segments": seg_out, "messages": msgs, "cards": cards,
    }
    (DOCS / f"sequence-{key}.sequence.json").write_text(json.dumps(spec, indent=2) + "\n")


build("ai-agent", "%AI.Agent tab: one chat turn, in call order",
      "App → Chat.Ask → Rust agent loop → model → LookupPatient → worker JOB → bs → bp → bo, one trace",
      1320,
      [("browser", "external", "Browser", "demo page"),
       ("app", "frontend", "Demo app", "chat turn span"),
       ("agent", "backend", "%AI.Agent", "Chat.Ask, Rust loop"),
       ("model", "cloud", "Model", "chat span"),
       ("tool", "backend", "LookupPatient", "execute_tool span"),
       ("worker", "backend", "Worker JOB", "RunLookup"),
       ("bs", "backend", "bs", "bs.ToolService"),
       ("bp", "backend", "bp", "bp.LookupBP"),
       ("bo", "backend", "bo", "bo.LookupBO"),
       ("collector", "messagebus", "Collector", "OTel Collector")],
      ["Turn",
       ("browser", "app", "POST /chat/ai-agent", "emphasis"),
       ("app", "agent", "Chat.Ask(q, traceparent): telemetry:context", "emphasis"),
       ("agent", "model", "chat (under invoke_agent)", "default"),
       ("model", "agent", "call LookupPatient", "return"),
       "Tool",
       ("agent", "tool", "execute_tool", "emphasis"),
       ("tool", "worker", "JOB, CurrentTraceparent()", "emphasis"),
       ("worker", "bs", "request, parent = tool span", "default"),
       ("bs", "bp", "PatientRequest + Traceparent", "default"),
       ("bp", "bo", "PatientRequest + Traceparent", "default"),
       ("bo", "bp", "summary", "return"),
       ("bp", "bs", "summary", "return"),
       ("bs", "worker", "summary", "return"),
       ("worker", "tool", "result", "return"),
       ("tool", "agent", "tool result", "return"),
       "Answer",
       ("agent", "model", "chat", "default"),
       ("model", "agent", "answer", "return"),
       ("agent", "app", "{content}", "return"),
       ("app", "browser", "reply + trace link", "return"),
       "Spans",
       ("app", "collector", "OTLP: chat turn", "dashed"),
       ("agent", "collector", "OTLP: invoke_agent, chat, execute_tool", "dashed"),
       ("bp", "collector", "OTLP: bs, bp, bo", "dashed")],
      None,
      [{"id": "handoff-1", "label": "App to Rust", "focus": ["app", "agent", "model"],
        "note": "telemetry:context hands the app's traceparent to the Rust loop, so invoke_agent nests under chat turn."},
       {"id": "handoff-2", "label": "Tool to production", "focus": ["tool", "worker", "bs", "bp", "bo"],
        "note": "CurrentTraceparent() hands the execute_tool span to a worker JOB; messages carry it on to bp and bo."},
       {"id": "export", "label": "Where spans go", "focus": ["app", "agent", "bp", "collector"],
        "note": "Three exporters, one collector. Only the collector talks to Langfuse."}],
      [{"dot": "cyan", "title": "The two hooks", "items": [
          "%AI.System.Configure(\"telemetry:context\") parents the Rust spans on the app's span",
          "%AI.Tool.CurrentTraceparent() hands the execute_tool span to the tool body",
          "Both come from the patched ai-core build, not a stock one"]},
       {"dot": "rose", "title": "Why a worker JOB", "items": [
          "Nested $ZF corrupts the outer frame (kernel CL 9598334 pending)",
          "So the tool runs the interop call in a JOB and passes only the traceparent",
          "The result comes back through ^IRIS.Temp"]},
       {"dot": "violet", "title": "Drawn last", "items": [
          "Spans are exported in batches while the turn runs",
          "They are drawn at the end so the call order stays readable"]}])

build("langchain", "LangChain tab: one chat turn, in call order",
      "App → run_turn (Python loop) → ChatIris → model → Chat.Lookup over the native API → bs → bp → bo, one trace",
      1320,
      [("browser", "external", "Browser", "demo page"),
       ("app", "frontend", "Demo app", "chat turn span"),
       ("loop", "backend", "run_turn", "invoke_agent span"),
       ("chatiris", "backend", "ChatIris", "iris_llm"),
       ("model", "cloud", "Model", "chat span"),
       ("lookup", "backend", "Chat.Lookup", "native API"),
       ("bs", "backend", "bs", "bs.ToolService"),
       ("bp", "backend", "bp", "bp.LookupBP"),
       ("bo", "backend", "bo", "bo.LookupBO"),
       ("collector", "messagebus", "Collector", "OTel Collector")],
      ["Turn",
       ("browser", "app", "POST /chat/langchain", "emphasis"),
       ("app", "loop", "run_turn(question)", "emphasis"),
       ("loop", "chatiris", "invoke(messages, tools)", "default"),
       ("chatiris", "model", "chat", "default"),
       ("model", "chatiris", "tool call", "return"),
       ("chatiris", "loop", "AIMessage.tool_calls", "return"),
       "Tool",
       ("loop", "lookup", "execute_tool: Lookup(id, traceparent)", "emphasis"),
       ("lookup", "bs", "Interop, parent = execute_tool", "default"),
       ("bs", "bp", "PatientRequest + Traceparent", "default"),
       ("bp", "bo", "PatientRequest + Traceparent", "default"),
       ("bo", "bp", "summary", "return"),
       ("bp", "bs", "summary", "return"),
       ("bs", "lookup", "summary", "return"),
       ("lookup", "loop", "ToolMessage", "return"),
       "Answer",
       ("loop", "chatiris", "invoke(+ tool result)", "default"),
       ("chatiris", "model", "chat", "default"),
       ("model", "chatiris", "answer", "return"),
       ("chatiris", "loop", "AIMessage", "return"),
       ("loop", "app", "answer", "return"),
       ("app", "browser", "reply + trace link", "return"),
       "Spans",
       ("app", "collector", "OTLP: chat turn, invoke_agent, chat, execute_tool", "dashed"),
       ("bp", "collector", "OTLP: bs, bp, bo", "dashed")],
      None,
      [{"id": "loop", "label": "Python owns the loop", "focus": ["app", "loop", "chatiris", "model"],
        "note": "run_turn emits invoke_agent and execute_tool itself. ChatIris is a leaf: one chat span per model call."},
       {"id": "tool", "label": "Same production", "focus": ["loop", "lookup", "bs", "bp", "bo"],
        "note": "The tool calls IRIS over the native API with the execute_tool traceparent. No worker JOB is needed here."},
       {"id": "export", "label": "Where spans go", "focus": ["app", "bp", "collector"],
        "note": "The app process exports every Python and iris_llm span; the production exports its own."}],
      [{"dot": "cyan", "title": "Same tree, other owner", "items": [
          "The span tree matches the %AI.Agent tab's",
          "Here the app emits invoke_agent and execute_tool, not the Rust core",
          "iris_llm uses the OTel API only; the app process owns the SDK"]},
       {"dot": "amber", "title": "The patch", "items": [
          "Issue #1: ChatIris dropped token usage",
          "The iris_llm wheel comes from the same patched build, 7440647"]}])

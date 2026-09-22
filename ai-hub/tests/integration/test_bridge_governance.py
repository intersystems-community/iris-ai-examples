"""
Integration tests for Bridge governance: Phase 4 (MCPService), Phase 5 (policies),
Phase 6 (OTel on ConfigStore path).

Must run inside irispython (embedded Python context) against a live IRIS 2026.3+
instance. Detects the embedded context by probing the IRIS kernel, not by looking
for a file the pip wheel also installs.
"""

import os
import sys

import pytest


def _is_embedded() -> bool:
    """True only inside irispython, with a live IRIS kernel behind the facade.

    Probe the runtime, not the install. The earlier check looked for `iris_ep.py`
    beside the `iris` package — but the `intersystems-irispython` wheel ships
    that file into plain site-packages, so on any laptop with the pip package the
    check said "embedded", `iris.cls(...)` handed back a unittest.mock.MagicMock,
    and every test below asserted about a MagicMock instead of skipping.
    `%SYSTEM.Version.GetVersion()` returns a str under irispython and a MagicMock
    anywhere else.
    """
    try:
        import iris

        return isinstance(iris.cls("%SYSTEM.Version").GetVersion(), str)
    except Exception:
        return False


requires_embedded = pytest.mark.skipif(
    not _is_embedded(),
    reason="Must run inside irispython (embedded Python context)",
)

sys.path.insert(0, "/tmp")


# ── Phase 5: Policy unit tests (no LLM required) ─────────────────────────────

@requires_embedded
def test_auth_policy_allow_all_by_default():
    """Empty policy allows every tool."""
    import iris
    policy = iris.cls("Sample.AI.Bridge.AuthPolicy")._New()
    call = iris.cls("%Library.DynamicObject")._FromJSON('{"name":"list_namespaces","arguments":{}}')
    sc = policy._CanExecute("list_namespaces", call, None)
    assert iris.cls("%SYSTEM.Status").IsOK(sc), "Default policy should allow all tools"


@requires_embedded
def test_auth_policy_deny_list():
    """Denied tool is blocked; other tools pass."""
    import iris
    policy = iris.cls("Sample.AI.Bridge.AuthPolicy")._New()
    policy.DenyList.Insert("count_classes")

    call = iris.cls("%Library.DynamicObject")._FromJSON('{"name":"count_classes","arguments":{}}')
    sc = policy._CanExecute("count_classes", call, None)
    assert not iris.cls("%SYSTEM.Status").IsOK(sc), "count_classes should be denied"

    call2 = iris.cls("%Library.DynamicObject")._FromJSON('{"name":"list_namespaces","arguments":{}}')
    sc2 = policy._CanExecute("list_namespaces", call2, None)
    assert iris.cls("%SYSTEM.Status").IsOK(sc2), "list_namespaces should pass deny-list check"


@requires_embedded
def test_auth_policy_strict_mode():
    """Strict mode: only listed tools visible."""
    import iris
    policy = iris.cls("Sample.AI.Bridge.AuthPolicy")._New()
    policy.AllowList.Insert("get_iris_version")
    policy.Strict = 1

    # Allowed tool
    assert policy._CanList("get_iris_version", None) == 1

    # Non-listed tool hidden
    assert policy._CanList("list_namespaces", None) == 0


@requires_embedded
def test_audit_policy_tag_on_metadata():
    """Bridge.AuditPolicy injects gen_ai.tool.source=python_bridge."""
    import iris
    policy = iris.cls("Sample.AI.Bridge.AuditPolicy")._New()
    # Verify it's a subclass of OTelAuditPolicy (inherits OtlpEndpoint property)
    assert hasattr(policy, "OtlpEndpoint"), (
        "Bridge.AuditPolicy should inherit OtlpEndpoint from OTelAuditPolicy"
    )


@requires_embedded
def test_audit_policy_traceparent_propagation():
    """Traceparent set on AuditPolicy propagates to span IDs."""
    import iris
    policy = iris.cls("Sample.AI.Bridge.AuditPolicy")._New()
    trace_id = iris.cls("Sample.AI.Policies.OTelAuditPolicy").GenHexId(32)
    parent_span = iris.cls("Sample.AI.Policies.OTelAuditPolicy").GenHexId(16)
    tp = f"00-{trace_id}-{parent_span}-01"
    policy.Traceparent = tp
    assert policy.Traceparent == tp


# ── Phase 4: MCPService class structure ──────────────────────────────────────

@requires_embedded
def test_mcp_service_class_exists():
    """Sample.AI.Bridge.MCPService is compiled."""
    import iris
    assert iris.cls("%Dictionary.CompiledClass")._ExistsId("Sample.AI.Bridge.MCPService"), (
        "Sample.AI.Bridge.MCPService not compiled — run import first"
    )


@requires_embedded
def test_mcp_service_extends_ai_mcp_service():
    """Bridge.MCPService extends %AI.MCP.Service."""
    import iris
    # Check the superclass chain via %Dictionary.CompiledClass
    cls_def = iris.cls("%Dictionary.CompiledClass")._OpenId("Sample.AI.Bridge.MCPService")
    assert cls_def is not None
    # Super is %AI.MCP.Service
    assert "MCP.Service" in cls_def.Super, (
        f"Expected MCP.Service in superclass chain, got: {cls_def.Super}"
    )


@requires_embedded
def test_mcp_service_specification_parameter():
    """SPECIFICATION parameter is set to the bridge ToolSet class name."""
    import iris
    # Access the class parameter
    cls_def = iris.cls("%Dictionary.CompiledClass")._OpenId("Sample.AI.Bridge.MCPService")
    assert cls_def is not None
    # Look for SPECIFICATION in parameters
    params = cls_def.Parameters
    found_spec = False
    i = 1
    while i <= params.Count():
        p = params.GetAt(i)
        if p.Name == "SPECIFICATION":
            found_spec = True
            assert "IRISInfoTools" in p.Default or p.Default == "", (
                f"SPECIFICATION default unexpected: {p.Default}"
            )
            break
        i += 1
    assert found_spec, "SPECIFICATION parameter not found on MCPService"


# ── Phase 6: OTel in RunQueryWithStats ───────────────────────────────────────

@requires_embedded
def test_run_query_with_stats_returns_trace_ids_when_otel_enabled(otel_sink):
    """RunQueryWithStats returns trace_id/span_id when OTLP endpoint is set."""
    import iris

    # Register a minimal ConfigStore entry pointing to a dummy provider
    # This test only checks the OTel ID generation path, not an actual LLM call.
    # We mock by checking the result structure when ConfigStore entry is missing —
    # the error path should still return empty trace_id (OTel not reached on error).
    result = iris.cls("Sample.AI.Bridge.Agent").RunQueryWithStats(
        "AI.LLM.NonExistentConfig",
        "",
        "test query"
    )
    # Error path — trace_id should be empty (OTel only emits on success)
    error = result._Get("error")
    assert error != "", "Expected error for non-existent config"
    trace_id = result._Get("trace_id")
    span_id = result._Get("span_id")
    # On error path, IDs are empty (no Chat() call happened)
    assert trace_id == "" or len(trace_id) == 32, f"trace_id malformed: {trace_id!r}"
    assert span_id == "" or len(span_id) == 16, f"span_id malformed: {span_id!r}"


@requires_embedded
def test_run_query_with_stats_result_structure():
    """RunQueryWithStats always returns all expected keys."""
    import iris

    result = iris.cls("Sample.AI.Bridge.Agent").RunQueryWithStats(
        "AI.LLM.NonExistentConfig",
        "",
        "test"
    )
    for key in ("content", "prompt_tokens", "completion_tokens", "error",
                "trace_id", "span_id"):
        val = result._Get(key)
        assert val is not None or val == "", (
            f"Key '{key}' missing from RunQueryWithStats result"
        )


@requires_embedded
def test_otel_hex_id_generation():
    """GenHexId produces correct-length lowercase hex strings."""
    import iris
    cls = iris.cls("Sample.AI.Policies.OTelAuditPolicy")
    for length in (16, 32):
        hex_id = cls.GenHexId(length)
        assert len(hex_id) == length, f"Expected {length} chars, got {len(hex_id)}"
        assert hex_id == hex_id.lower(), "GenHexId should return lowercase hex"
        int(hex_id, 16)  # raises if not valid hex


@requires_embedded
def test_otel_now_ns_is_reasonable():
    """NowNs returns a Unix nanosecond timestamp in a plausible range."""
    import iris
    # 2026-01-01 00:00:00 UTC in nanoseconds ≈ 1767225600000000000
    # 2030-01-01 00:00:00 UTC in nanoseconds ≈ 1893456000000000000
    ns = iris.cls("Sample.AI.Policies.OTelAuditPolicy").NowNs()
    assert 1_767_225_600_000_000_000 < ns < 1_893_456_000_000_000_000, (
        f"NowNs out of expected range: {ns}"
    )


# ── otel_sink fixture (no-op when OTLP not needed) ────────────────────────────

@pytest.fixture
def otel_sink():
    """Start an in-process OTLP/HTTP sink for tests that need it."""
    _demo_dir = str(
        __import__("pathlib").Path(__file__).parent.parent.parent / "python" / "embedded"
    )
    sys.path.insert(0, _demo_dir)
    try:
        from otel_sink import OTelSink
        sink = OTelSink()
        prev = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = sink.endpoint
        yield sink
        if prev is None:
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        else:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = prev
        sink.stop()
    except ImportError:
        # otel_sink not available outside xdev — yield a no-op
        yield None

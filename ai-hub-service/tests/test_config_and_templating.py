"""The config language: env expansion, extends/merge, validation, templates."""

from __future__ import annotations

import pytest
from conftest import EXAMPLES

from aihub_service.config import ConfigError, build_config, expand_env, load_config, merge
from aihub_service.templating import render, truthy


def test_env_expansion_uses_value_then_default_then_fails():
    assert expand_env("${A:-x}", {"A": "set"}) == "set"
    assert expand_env("${A:-x}", {}) == "x"
    assert expand_env("${A:-}", {}) == ""
    assert expand_env("${A:-x}", {"A": ""}) == "x"
    with pytest.raises(ConfigError, match="A is not set"):
        expand_env("${A}", {})


def test_merge_rebinds_one_named_tool_and_keeps_the_rest():
    base = {"tools": [{"name": "a", "effect": "read"}, {"name": "b", "effect": "write"}]}
    out = merge(base, {"tools": [{"name": "b", "backend": "x"}]})
    assert out["tools"] == [{"name": "a", "effect": "read"}, {"name": "b", "effect": "write", "backend": "x"}]


@pytest.mark.parametrize("mode", ["offline", "inplace", "sidecar"])
def test_every_mode_keeps_the_shared_governance(mode):
    cfg = load_config(EXAMPLES / f"{mode}.yaml", environ={})
    assert cfg.mode == mode
    effects = {t["name"]: t["effect"] for t in cfg.tools}
    assert effects["TriggerFollowUp"] == "write" and effects["StartProduction"] == "write"
    assert all(t.get("backend") for t in cfg.tools), "a mode left a tool unbound"
    assert set(cfg.agents) == {"sdoh-assessment", "sdoh-assistant", "sdoh-decision-gate"}


def test_sidecar_splits_tools_between_legacy_and_companion():
    cfg = load_config(EXAMPLES / "sidecar.yaml", environ={})
    by_backend = {}
    for t in cfg.tools:
        by_backend.setdefault(t["backend"], set()).add(t["name"])
    assert by_backend["legacy"] == {
        "SearchPatients", "FetchPatientSummary", "TriggerFollowUp",
        "GetInteropTraces", "GetProductionStatus", "StartProduction",
    }
    assert by_backend["companion"] == {
        "SearchSDoHProtocols", "AssessSDoHRisk", "DraftCarePlan",
        "SearchClinicalNotes",
    }
    assert by_backend["liquid"] == {"DecideCareAction"}


def test_environment_moves_the_backends():
    cfg = load_config(EXAMPLES / "sidecar.yaml",
                      environ={"LEGACY_IRIS_HOST": "trak-prod-1", "AIHUB_MCP_URL": "http://c:8888/mcp/x"})
    assert cfg.backends["legacy"]["host"] == "trak-prod-1"
    assert cfg.backends["companion"]["url"] == "http://c:8888/mcp/x"


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"backends": {}, "tools": [{"name": "t", "backend": "nope"}]}, "not declared"),
        ({"backends": {"b": {}}, "tools": [{"name": "t", "backend": "b"}] * 2}, "duplicate"),
        ({"backends": {"b": {}}, "tools": [{"name": "t", "backend": "b", "effect": "delete"}]}, "effect"),
        ({"backends": {"b": {}}, "tools": [], "agents": {"a": {"tools": ["t"]}}}, "unknown tools"),
        (
            {"backends": {"b": {}}, "tools": [{"name": "t", "backend": "b"}],
             "agents": {"a": {"tools": [], "playbook": {"steps": [{"tool": "t"}]}}}},
            "not in the agent's tools",
        ),
    ],
)
def test_config_mistakes_are_named(raw, message):
    with pytest.raises(ConfigError, match=message):
        build_config(raw, environ={})


def test_render_keeps_types_for_whole_references_and_filters():
    scope = {"context": {"followUp": True, "q": "Maria"}, "result": {}}
    assert render("${context.followUp}", scope) is True
    assert render("%${context.q|lower}%", scope) == "%maria%"
    assert render("${context.missing|default:routine}", scope) == "routine"
    assert render({"a": ["${context.q}"]}, scope) == {"a": ["Maria"]}


def test_truthy_conditions():
    scope = {"context": {"followUp": "true"}, "result": {"A": "Overall Priority: URGENT (5/6)"}}
    assert truthy("result.A contains 'URGENT'", scope)
    assert truthy("context.followUp and not result.A contains 'ROUTINE'", scope)
    assert not truthy("context.missing or result.A == 'x'", scope)
    assert truthy(None, scope) and not truthy(False, scope)
    with pytest.raises(ValueError):
        truthy("result.A >> 3", scope)

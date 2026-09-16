"""Tests for the stdio entrypoint's environment-variable handling, without
actually running a server (no event loop, no IRIS).
"""

from __future__ import annotations

import pytest

import mcp_iris.__main__ as entrypoint


def test_main_requires_iris_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IRIS_HOSTNAME", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        entrypoint.main()

    assert exc_info.value.code == 2


def test_env_int_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_IRIS_ROW_CAP", raising=False)
    assert entrypoint._env_int("MCP_IRIS_ROW_CAP", 1000) == 1000


def test_env_int_parses_set_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_IRIS_ROW_CAP", "50")
    assert entrypoint._env_int("MCP_IRIS_ROW_CAP", 1000) == 50


def test_env_float_parses_set_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_IRIS_QUERY_TIMEOUT_SECONDS", "12.5")
    assert entrypoint._env_float("MCP_IRIS_QUERY_TIMEOUT_SECONDS", 30.0) == 12.5


def test_main_builds_server_and_calls_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IRIS_HOSTNAME", "localhost")
    monkeypatch.setenv("IRIS_NAMESPACE", "USER")

    calls: dict[str, object] = {}

    class FakeServer:
        def run(self, transport: str) -> None:
            calls["transport"] = transport

    def fake_build_server(executor: object) -> FakeServer:
        calls["executor"] = executor
        return FakeServer()

    monkeypatch.setattr(entrypoint, "build_server", fake_build_server)

    entrypoint.main()

    assert calls["transport"] == "stdio"
    assert calls["executor"] is not None

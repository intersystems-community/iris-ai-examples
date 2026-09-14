"""
Integration tests for JiraTools / JiraAgent — Atlassian Rovo MCP Server.

Two test levels:

1. Contract tests (no credentials, always run):
   - JiraTools.cls XData structure
   - JiraAgent classmethods exist
   - OTelAuditPolicy class structure

2. Live e2e (requires ATLASSIAN_API_TOKEN in env):
   - Rovo MCP server reachable
   - initialize handshake returns tool list
   - tools/list returns Teamwork Graph tools

Set ATLASSIAN_API_TOKEN to run live tests. Token from:
  https://id.atlassian.com/manage-profile/security/api-tokens
Or load from aicore/.env before running:
  set -a && source /path/to/aicore/.env && set +a
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import pytest

# ── paths ─────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent.parent
_CLS_ROOT  = _REPO_ROOT / "objectscript" / "cls"

ROVO_URL = "https://mcp.atlassian.com/v1/mcp/authv2"

def _load_token() -> str:
    """Return ATLASSIAN_API_TOKEN from env, falling back to aicore/.env file."""
    token = os.environ.get("ATLASSIAN_API_TOKEN", "")
    if token:
        return token
    env_file = _REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ATLASSIAN_API_TOKEN=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return ""

_TOKEN = _load_token()

requires_token = pytest.mark.skipif(
    not _TOKEN,
    reason="ATLASSIAN_API_TOKEN not set — load from aicore/.env to run live tests",
)


# ── helpers ───────────────────────────────────────────────────────────────────

_COMMON_HEADERS = {
    "Authorization": f"Bearer {_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    # Cloudflare 1010 blocks the default Python UA
    "User-Agent": "Mozilla/5.0 (compatible; iris-ai-examples-test/0.1)",
}


def _mcp_raw(method: str, params: dict | None = None,
             session_id: str | None = None) -> tuple[dict, str]:
    """Send one MCP request; return (parsed_result, session_id)."""
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method,
        "params": params or {},
    }).encode()
    headers = dict(_COMMON_HEADERS)
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(ROVO_URL, data=body, headers=headers)
    resp = urllib.request.urlopen(req, timeout=15)
    new_session_id = resp.headers.get("Mcp-Session-Id", session_id or "")
    raw = resp.read().decode()
    for line in raw.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip()), new_session_id
    raise ValueError(f"No data: line in response: {raw[:200]}")


def _mcp_session() -> tuple[dict, str]:
    """Initialize a session; return (initialize_result, session_id)."""
    result, sid = _mcp_raw("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "iris-ai-examples-test", "version": "0.1"},
    })
    return result, sid


def _mcp_request(method: str, params: dict | None = None) -> dict:
    """Initialize a session then call method; returns the result object."""
    _, sid = _mcp_session()
    result, _ = _mcp_raw(method, params, session_id=sid)
    return result


# ── contract tests (no credentials) ──────────────────────────────────────────

def test_jira_tools_cls_file_exists():
    """JiraTools.cls is present in the repo."""
    path = _CLS_ROOT / "Sample" / "AI" / "Tools" / "JiraTools.cls"
    assert path.exists(), f"Not found: {path}"


def test_jira_tools_xdata_has_mcp_remote():
    """JiraTools.cls XData contains the Rovo MCP Remote element."""
    path = _CLS_ROOT / "Sample" / "AI" / "Tools" / "JiraTools.cls"
    content = path.read_text()
    assert "mcp.atlassian.com" in content, "Missing Rovo MCP URL"
    assert "AuthType=\"bearer\"" in content, "Missing bearer auth"
    assert "@{env:ATLASSIAN_API_TOKEN}" in content, "Missing token placeholder"
    assert "<Remote" in content and "<MCP" in content, "Missing MCP/Remote XML"


def test_jira_tools_extends_toolset():
    """JiraTools.cls extends %AI.ToolSet."""
    path = _CLS_ROOT / "Sample" / "AI" / "Tools" / "JiraTools.cls"
    content = path.read_text()
    assert "Extends %AI.ToolSet" in content, "JiraTools should extend %AI.ToolSet"


def test_jira_agent_cls_file_exists():
    """JiraAgent.cls is present in the repo."""
    path = _CLS_ROOT / "Sample" / "AI" / "Examples" / "JiraAgent.cls"
    assert path.exists(), f"Not found: {path}"


def test_jira_agent_has_required_classmethods():
    """JiraAgent has Demo, Ask, SearchIssues, FetchIssue classmethods."""
    path = _CLS_ROOT / "Sample" / "AI" / "Examples" / "JiraAgent.cls"
    content = path.read_text()
    for method in ("Demo", "Ask", "SearchIssues", "FetchIssue"):
        assert f"ClassMethod {method}" in content, f"Missing ClassMethod {method}"


def test_jira_agent_uses_instance_form():
    """JiraAgent uses ##class(...).%New() not the string 'iris:' URI form."""
    path = _CLS_ROOT / "Sample" / "AI" / "Examples" / "JiraAgent.cls"
    content = path.read_text()
    assert "iris:Sample.AI.Tools.JiraTools" not in content, (
        "JiraAgent must not use the 'iris:ClassName' string form — "
        "it causes a re-entrant callin crash. Use ##class(...).%New() instead."
    )
    assert '##class(Sample.AI.Tools.JiraTools).%New()' in content, (
        "JiraAgent must use ##class(Sample.AI.Tools.JiraTools).%New()"
    )


def test_jira_agent_checks_token_before_run():
    """JiraAgent verifies ATLASSIAN_API_TOKEN before attempting any LLM call."""
    path = _CLS_ROOT / "Sample" / "AI" / "Examples" / "JiraAgent.cls"
    content = path.read_text()
    assert "ATLASSIAN_API_TOKEN" in content, (
        "JiraAgent should check ATLASSIAN_API_TOKEN env var"
    )


# ── live e2e (ATLASSIAN_API_TOKEN required) ───────────────────────────────────

@requires_token
def test_rovo_mcp_initialize():
    """Atlassian Rovo MCP Server responds to initialize with protocol version."""
    resp = _mcp_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "iris-ai-examples-test", "version": "0.1"},
    })
    assert "result" in resp, f"No result in response: {resp}"
    result = resp["result"]
    assert result.get("protocolVersion") == "2024-11-05"
    assert "serverInfo" in result
    assert result["serverInfo"].get("name") == "atlassian-mcp-server"


@requires_token
def test_rovo_mcp_tools_list():
    """tools/list returns at least the Teamwork Graph tools."""
    # Must initialize first (stateful SSE session) — but since each request
    # is stateless HTTP here, tools/list directly returns the catalog.
    resp = _mcp_request("tools/list")
    assert "result" in resp, f"No result: {resp}"
    tools = resp["result"].get("tools", [])
    tool_names = {t["name"] for t in tools}
    # Rovo exposes Teamwork Graph tools
    expected = {"getTeamworkGraphContext", "getTeamworkGraphObject",
                "addTeamworkGraphContext"}
    found = expected & tool_names
    assert found, (
        f"Expected at least one Teamwork Graph tool, got: {tool_names}"
    )


@requires_token
def test_rovo_mcp_tools_have_input_schema():
    """Every tool returned by tools/list has a valid inputSchema."""
    resp = _mcp_request("tools/list")
    tools = resp.get("result", {}).get("tools", [])
    assert tools, "tools/list returned no tools"
    for tool in tools:
        assert "name" in tool, f"Tool missing name: {tool}"
        assert "inputSchema" in tool, f"Tool {tool['name']} missing inputSchema"
        schema = tool["inputSchema"]
        assert isinstance(schema, dict), f"inputSchema not a dict for {tool['name']}"

"""
End-to-end tests for the Sample.AI.OAuth example against a live IdP.

The companion suite, test_oauth_rbac.py, runs inside irispython and mocks
$Roles. This one runs on the host with nothing but the standard library, and
mocks nothing: it fetches real tokens from a real IdP and drives real MCP
requests through the sidecar. It is the suite that can falsify the measured
matrix in the example's README.

Two environment variables:

    MCP_OAUTH_ENDPOINT   the MCP endpoint through the sidecar, e.g.
                         http://localhost:55888/mcp/sampleoauth
    MCP_OAUTH_IDP_URL    the IdP base URL (default http://localhost:55880,
                         which is what fixtures/keycloak publishes)

Everything skips unless both answer. Start the IdP with:

    cd fixtures/keycloak && docker compose up -d --wait

The endpoint must also be listed in the sidecar's `endpoints` config. A sidecar
that is running but does not serve this path answers 401 like a healthy one, so
these tests fail rather than skip in that case — deliberately. A silent skip
there would hide a broken deployment.

Run:
    pytest tests/integration/test_oauth_live_idp.py -v
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

IDP_URL = os.environ.get("MCP_OAUTH_IDP_URL", "http://localhost:55880").rstrip("/")
IDP_REALM = os.environ.get("MCP_OAUTH_IDP_REALM", "aihub")
ENDPOINT = os.environ.get("MCP_OAUTH_ENDPOINT", "").rstrip("/")

# Tool names arrive through the sidecar prefixed with mcp_<app>_. An unprefixed
# name comes back as "no registered service found for tool", which reads like a
# permission error and is not one.
TOOL_PREFIX = os.environ.get("MCP_OAUTH_TOOL_PREFIX", "")

# scope -> (client, secret, the one tool that tier may see)
TIERS = {
    "read": ("mcp-read", "read-secret", "GetStatus"),
    "write": ("mcp-write", "write-secret", "WriteNote"),
    "admin": ("mcp-admin", "admin-secret", "AdminReset"),
}

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


# ── HTTP plumbing ───────────────────────────────────────────────────────────


def _post(url, data, headers, timeout=15):
    """POST and return (status, headers, body_text). HTTP errors are results,
    not exceptions — a 401 is a thing these tests assert on."""
    if isinstance(data, dict):
        body = urllib.parse.urlencode(data).encode()
    elif isinstance(data, (bytes, bytearray)):
        body = bytes(data)
    else:
        body = str(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read().decode(errors="replace")


def _reachable(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as exc:
        # Something is listening and speaking HTTP — but 404 means this path is
        # not configured on it, which is a skip, not a failure. A sidecar that
        # has dropped the endpoint from its config answers exactly that way.
        return exc.code not in (404, 410)
    except Exception:
        return False


def _token(tier):
    client, secret, _ = TIERS[tier]
    status, _, body = _post(
        f"{IDP_URL}/realms/{IDP_REALM}/protocol/openid-connect/token",
        {
            "grant_type": "client_credentials",
            "client_id": client,
            "client_secret": secret,
        },
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200, f"IdP refused the {tier} client: {status} {body}"
    return json.loads(body)["access_token"]


def _claims(token):
    """Decode a JWT payload without verifying it. Fine here — these assertions
    are about what the fixture minted, and IRIS is what verifies."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _sse_json(body):
    """Pull the JSON-RPC object out of an SSE body. The endpoint answers
    `data: {...}` rather than a plain JSON body.

    The first event is an empty `data:` keep-alive followed by `id:` and
    `retry:`, so taking the first data line and parsing it fails on every
    single response. Skip payloads that are not JSON."""
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload.startswith("{"):
            return json.loads(payload)
    if body.strip().startswith("{"):
        return json.loads(body)
    return None


# ── MCP protocol ────────────────────────────────────────────────────────────


def _handshake(auth):
    """initialize + notifications/initialized. Returns (status, session_id).

    session_id is None when the endpoint refused, which is the interesting case
    for the negative tests.
    """
    headers = dict(MCP_HEADERS)
    if auth is not None:
        headers["Authorization"] = auth
    status, resp_headers, _ = _post(
        ENDPOINT,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "live-idp-test", "version": "0"},
                },
            }
        ),
        headers,
    )
    session = None
    for key, value in resp_headers.items():
        if key.lower() == "mcp-session-id":
            session = value
    if session:
        headers["Mcp-Session-Id"] = session
        _post(
            ENDPOINT,
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            headers,
        )
    return status, session


def _rpc(auth, session, method, params, req_id=2):
    headers = dict(MCP_HEADERS)
    if auth is not None:
        headers["Authorization"] = auth
    if session:
        headers["Mcp-Session-Id"] = session
    status, _, body = _post(
        ENDPOINT,
        json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        ),
        headers,
    )
    return status, _sse_json(body)


def _prefix():
    """The prefix the sidecar puts on this endpoint's tool names."""
    if TOOL_PREFIX:
        return TOOL_PREFIX
    app = urllib.parse.urlparse(ENDPOINT).path.rstrip("/").rsplit("/", 1)[-1]
    return f"mcp_{app}_"


def _qualified(bare_name):
    """The tool name as the sidecar publishes it. The bare name is refused with
    'no registered service found', which reads like a permission error."""
    return f"{_prefix()}{bare_name}"


def _tool_names(auth, session):
    """Only this endpoint's tools.

    One catalog covers the whole sidecar: every configured endpoint's tools plus
    the sidecar's own `iris_status`. So a role assertion has to scope itself to
    this endpoint's prefix — a bare count over `tools/list` measures how many
    other endpoints happen to be configured, not what the token permits."""
    status, msg = _rpc(auth, session, "tools/list", {})
    assert status == 200, f"tools/list returned {status}"
    tools = (msg or {}).get("result", {}).get("tools", [])
    prefix = _prefix()
    return [t["name"] for t in tools if t["name"].startswith(prefix)]


# ── Gates ───────────────────────────────────────────────────────────────────

requires_stack = pytest.mark.skipif(
    not ENDPOINT
    or not _reachable(f"{IDP_URL}/realms/{IDP_REALM}/.well-known/openid-configuration")
    or not _reachable(ENDPOINT),
    reason=(
        "needs MCP_OAUTH_ENDPOINT set and both the IdP and the MCP endpoint "
        "answering (see fixtures/keycloak/)"
    ),
)

pytestmark = requires_stack


# ── The fixture is what the example documents ───────────────────────────────


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_token_carries_the_scope_and_audience_the_example_expects(tier):
    """Guards against fixture drift. If the realm stops emitting the scope or
    the audience, every test below fails for a reason that looks like IRIS."""
    claims = _claims(_token(tier))
    assert f"mcp.{tier}" in claims.get("scope", "").split()

    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    assert "mcp-api" in audiences, (
        "no mcp-api in aud — the mcp.audience client scope is missing its "
        "oidc-audience-mapper, and IRIS will reject the token without saying why"
    )


# ── Catalog filtering ───────────────────────────────────────────────────────


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_each_tier_sees_exactly_its_own_tool(tier):
    expected = TIERS[tier][2]
    # One token for the whole session. Fetching a second one and sending that
    # instead is a different test — see test_swapping_the_token_mid_session.
    auth = f"Bearer {_token(tier)}"
    status, session = _handshake(auth)
    assert status == 200, f"handshake refused for {tier}: {status}"
    assert session, f"no mcp-session-id returned for {tier}"

    names = _tool_names(auth, session)
    assert len(names) == 1, f"{tier} saw {names}, expected one tool"
    assert names[0].endswith(expected)


@pytest.mark.parametrize("swap_to", ["read", "admin"])
def test_swapping_the_token_mid_session_drops_the_endpoint(swap_to):
    """Present a different token on a live session and this endpoint stops
    contributing tools — including when the new token is a *fresh token for the
    same tier*, and including when it is a higher tier. Fail-closed, and
    recoverable: send the original token again and the tool is back.

    Measured on iris-mcp-server against 2026.3.0AI build 139U. It matters for
    clients that refresh a token on a schedule rather than per connection: the
    refresh does not re-authorize the session, it silently empties it.
    """
    auth = f"Bearer {_token('read')}"
    status, session = _handshake(auth)
    assert status == 200 and session
    assert _tool_names(auth, session), "read tier saw nothing before the swap"

    other = f"Bearer {_token(swap_to)}"
    assert other != auth, "expected a distinct token to swap to"
    assert _tool_names(other, session) == [], (
        "a swapped token was honoured mid-session — if this fails on your "
        "sidecar build, a client could change tier without reconnecting"
    )

    assert _tool_names(auth, session), "the original token did not recover"


def test_the_three_tiers_do_not_leak_into_each_other():
    """Three client sessions back to back against one running sidecar. This is
    the claim that does not hold on every sidecar build — the README says so,
    and this is the test that checks it on yours."""
    seen = {}
    for tier in sorted(TIERS):
        auth = f"Bearer {_token(tier)}"
        status, session = _handshake(auth)
        assert status == 200 and session
        seen[tier] = sorted(_tool_names(auth, session))

    for tier, names in seen.items():
        assert len(names) == 1, f"{tier} saw {names}"
        assert names[0].endswith(TIERS[tier][2])
    assert len({tuple(v) for v in seen.values()}) == 3, f"tiers overlapped: {seen}"


# ── Execution ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_a_tier_can_call_its_own_tool(tier):
    auth = f"Bearer {_token(tier)}"
    status, session = _handshake(auth)
    assert status == 200 and session

    tool = _qualified(TIERS[tier][2])
    args = {"pNote": "live-idp test"} if TIERS[tier][2] == "WriteNote" else {}
    status, msg = _rpc(auth, session, "tools/call", {"name": tool, "arguments": args})
    assert status == 200, f"tools/call returned {status}"
    assert msg and "result" in msg, f"tools/call gave {msg}"
    text = json.dumps(msg["result"])
    assert "no registered service found" not in text, text


def test_calling_another_tiers_tool_is_refused():
    """Refused by the sidecar, before RBACPolicy.%CanExecute is reached: the
    tool is not in this session's registry at all. Execution enforcement is
    defence in depth behind the catalog, not the first line of it."""
    auth = f"Bearer {_token('read')}"
    status, session = _handshake(auth)
    assert status == 200 and session

    status, msg = _rpc(
        auth, session, "tools/call", {"name": _qualified("AdminReset"), "arguments": {}}
    )
    text = json.dumps(msg)
    assert "Admin reset initiated" not in text, f"the tool actually ran: {text}"
    assert ("error" in msg) or msg.get("result", {}).get("isError"), text
    assert "no registered service found" in text, text


# ── Negative cases ──────────────────────────────────────────────────────────


def test_a_garbage_bearer_token_contributes_no_tools():
    """OnAuthenticate returns an error status and this endpoint contributes
    nothing. Two things this deliberately does not assert: that the caller gets
    a 401 (the sidecar may still complete a session), and that the catalog is
    empty (other endpoints on the same sidecar keep publishing their tools —
    only this endpoint's prefix disappears)."""
    auth = "Bearer not-a-jwt"
    status, session = _handshake(auth)
    if not session:
        return  # refused outright, which is also correct
    assert _tool_names(auth, session) == []


def test_no_authorization_header_never_reaches_iris():
    status, session = _handshake(None)
    assert status == 401, f"expected the sidecar to answer 401, got {status}"
    assert not session

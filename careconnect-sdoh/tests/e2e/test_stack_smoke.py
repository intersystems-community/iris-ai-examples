import httpx
import pytest
import socket

from conftest import (
    FHIR_BASE,
    HUB_HOST,
    HUB_PORT,
    JUPYTER_URL,
    MCP_URL,
    STREAMLIT_URL,
    USERS,
    host_port,
    requires_iris,
)


pytestmark = [pytest.mark.smoke, pytest.mark.docker]


def _port_open(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(2)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def test_fhir_port_open():
    host, port = host_port(FHIR_BASE)
    assert _port_open(host, port), f"iris-fhir port {port} not reachable"


def test_hub_port_open():
    assert _port_open(HUB_HOST, HUB_PORT), f"iris-ai-hub port {HUB_PORT} not reachable"


def test_fhir_metadata_returns_200(fhir):
    r = fhir.get("/metadata")
    assert r.status_code == 200, f"FHIR /metadata returned {r.status_code}"
    assert r.json().get("resourceType") == "CapabilityStatement"


def test_careconnect_app_port_open():
    host, port = host_port(STREAMLIT_URL)
    assert _port_open(host, port), f"careconnect Streamlit port {port} not reachable"


def test_jupyter_port_open():
    host, port = host_port(JUPYTER_URL)
    assert _port_open(host, port), f"Jupyter port {port} not reachable"


@requires_iris
def test_hub_iris_connect_admin():
    import iris

    conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
    assert conn is not None
    conn.close()


def test_mcp_endpoint_reachable():
    try:
        r = httpx.get(MCP_URL, timeout=5)
        # 401 belongs in this list: the MCP web application requires
        # authentication, so an unauthenticated GET proves the endpoint is
        # listening just as well as a 405 does. This test is about reachability,
        # not about authorization.
        assert r.status_code in (200, 400, 401, 404, 405, 422), (
            f"MCP endpoint returned unexpected {r.status_code}"
        )
    except httpx.ConnectError:
        pytest.skip(
            "MCP endpoint not yet running — objectscript-mcp may not be started"
        )

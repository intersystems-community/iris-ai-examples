import httpx
import pytest
import socket

from conftest import FHIR_BASE, HUB_HOST, HUB_PORT, MCP_URL, USERS, requires_iris


pytestmark = [pytest.mark.smoke, pytest.mark.docker]


def _port_open(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(2)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def test_fhir_port_open():
    assert _port_open("localhost", 55773), "iris-fhir port 55773 not reachable"


def test_hub_port_open():
    assert _port_open(HUB_HOST, HUB_PORT), f"iris-ai-hub port {HUB_PORT} not reachable"


def test_fhir_metadata_returns_200():
    r = httpx.get(f"{FHIR_BASE}/metadata", timeout=10)
    assert r.status_code == 200, f"FHIR /metadata returned {r.status_code}"
    assert r.json().get("resourceType") == "CapabilityStatement"


def test_careconnect_app_port_open():
    assert _port_open("localhost", 55501), (
        "careconnect Streamlit port 55501 not reachable"
    )


def test_jupyter_port_open():
    assert _port_open("localhost", 55888), "Jupyter port 55888 not reachable"


@requires_iris
def test_hub_iris_connect_admin():
    import iris

    conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
    assert conn is not None
    conn.close()


def test_mcp_endpoint_reachable():
    try:
        r = httpx.get(MCP_URL, timeout=5)
        assert r.status_code in (200, 404, 405), (
            f"MCP endpoint returned unexpected {r.status_code}"
        )
    except httpx.ConnectError:
        pytest.skip(
            "MCP endpoint not yet running — objectscript-mcp may not be started"
        )

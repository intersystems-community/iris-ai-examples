import base64
import os
import socket
import subprocess
import time

import httpx
import pytest

# Defaults are the ports docker-compose.yml publishes, so `make up` followed by
# `make test-smoke` works with no environment set. Override any of them to point at
# a stack on other ports.
FHIR_BASE = os.environ.get(
    "FHIR_BASE", "http://localhost:52774/csp/healthshare/demo/fhir/r4"
)
HUB_HOST = os.environ.get("HUB_HOST", "localhost")
HUB_PORT = int(os.environ.get("HUB_PORT", "1973"))
HUB_NS = os.environ.get("HUB_NS", "USER")
MCP_URL = os.environ.get("MCP_URL", "http://localhost:8888/mcp/careconnect")
JUPYTER_URL = os.environ.get("JUPYTER_URL", "http://localhost:8889")
IVG_BASE = os.environ.get("IVG_BASE", "http://localhost:19800")
IVG_API_KEY = os.environ.get("IVG_API_KEY", "changeme")

SKIP_IRIS = os.environ.get("SKIP_IRIS_TESTS", "false").lower() == "true"

USERS = {
    "chw": ("chw_user", "chw_pass"),
    "chw_senior": ("chw_sr", "chw_sr_pass"),
    "admin": ("_SYSTEM", "SYS"),
    "readonly": ("ro_user", "ro_pass"),
    "case_manager": ("cm_user", "cm_pass"),
}

requires_iris = pytest.mark.skipif(
    SKIP_IRIS,
    reason="SKIP_IRIS_TESTS=true — set to false to run against live test stack",
)


def _iris_connect(username: str, password: str):
    import iris

    return iris.connect(HUB_HOST, HUB_PORT, HUB_NS, username, password)


def _get_user_roles(conn) -> str:
    import iris

    iris_obj = iris.createIRIS(conn)
    try:
        return (
            iris_obj.classMethodValue(
                "%SYSTEM.Security", "GetUserRoles", USERS["admin"][0]
            )
            or ""
        )
    except Exception:
        cur = conn.cursor()
        cur.execute("SELECT Roles FROM Security.Users WHERE Name = ?", [conn.username])
        row = cur.fetchone()
        return row[0] if row else ""


def _basic_auth(username: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


def _fhir_client() -> httpx.Client:
    return httpx.Client(base_url=FHIR_BASE, timeout=15)


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


@pytest.fixture(scope="function")
def iris_conn_admin():
    conn = _iris_connect(*USERS["admin"])
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def iris_conn_chw():
    conn = _iris_connect(*USERS["chw"])
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def iris_conn_readonly():
    conn = _iris_connect(*USERS["readonly"])
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def fhir():
    with _fhir_client() as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def docker_test_stack(request):
    # Unit tests never need Docker — skip fixture entirely for unit-only runs
    markers = {m.name for item in request.session.items for m in item.own_markers}
    if not markers.intersection({"docker", "smoke", "contract", "e2e", "ivg"}):
        yield
        return

    # Every `make test-*` target sets SKIP_DOCKER_UP=true and expects the demo stack to
    # be up already (`make up`, or `make up-ivg` for the ivg-marked tests). This branch
    # is the convenience path for running pytest directly.
    if os.environ.get("SKIP_DOCKER_UP", "false").lower() == "true":
        yield
        return

    compose_file = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")
    if not os.path.exists(compose_file):
        pytest.skip("docker-compose.yml not found — run from the example root")

    # The IVG services are profile-gated; without --profile ivg they never start.
    up = ["docker", "compose", "-f", compose_file]
    if "ivg" in markers:
        up += ["--profile", "ivg"]
    subprocess.run(up + ["up", "-d", "--wait"], check=True, timeout=600)
    _wait_healthy(timeout=120)
    yield
    # Deliberately no `down -v` here: this is the demo stack, and tearing it down (let
    # alone dropping its volumes) at the end of a test run is not what someone running
    # pytest against a live demo expects. Stop it with `make down` when you are done.


def _wait_healthy(timeout: int = 120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{FHIR_BASE}/metadata", timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(5)
    pytest.fail(f"FHIR endpoint not healthy after {timeout}s")

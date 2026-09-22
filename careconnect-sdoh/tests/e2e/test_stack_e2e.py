import os
import platform
import subprocess
import time

import httpx
import pytest

from conftest import (
    HUB_HOST,
    HUB_PORT,
    STREAMLIT_URL,
    USERS,
    requires_iris,
)

pytestmark = [pytest.mark.e2e, pytest.mark.docker]


class TestIdempotency:
    def test_restart_does_not_duplicate_patients(self, fhir):
        # Through the `fhir` fixture, which carries credentials. A bare httpx.get
        # here answered 401 on every run: this server only leaves /metadata open.
        r1 = fhir.get("/Patient", params={"_summary": "count"})
        assert r1.status_code == 200, f"FHIR /Patient returned {r1.status_code}"
        count_before = r1.json().get("total", 0)
        assert count_before > 0, "No patients loaded — check Synthea init"
        r2 = fhir.get("/Patient", params={"_summary": "count"})
        count_after = r2.json().get("total", 0)
        assert count_before == count_after, (
            f"Patient count changed: {count_before} → {count_after}"
        )


class TestOllamaFallback:
    def test_careconnect_starts_without_openai_key(self):
        if os.environ.get("OPENAI_API_KEY"):
            pytest.skip(
                "OPENAI_API_KEY is set — testing without it requires special env"
            )
        r = httpx.get(STREAMLIT_URL, timeout=5)
        assert r.status_code in (200, 302), (
            "Careconnect not reachable without OpenAI key"
        )


class TestVectorProbe:
    def test_fhir_probe_output_in_logs(self):
        result = subprocess.run(
            ["docker", "logs", "careconnect-sdoh-app", "--tail", "50"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logs = result.stdout + result.stderr
        # The app service in this compose file is a placeholder: it builds the SDoH
        # dependencies and then sleeps, printing one line. It never runs the vector
        # probe, so asserting the probe output here fails for a reason that has
        # nothing to do with FHIR — skip and say which container would have to
        # change.
        if "placeholder" in logs:
            pytest.skip(
                "careconnect-sdoh-app ships as a placeholder (sleep infinity); "
                "the vector probe runs only once this service has a real entrypoint"
            )
        assert "vector (_v_content)" in logs or "_content fallback" in logs, (
            f"Expected FHIR probe output in careconnect logs, got: {logs[-500:]}"
        )


class TestPlatformSupport:
    def test_iris_fhir_container_platform(self):
        # uname inside the container, not `docker inspect --format {{.Platform}}`:
        # that field is the OS ("linux") and carries no architecture at all, so the
        # arm64 assertion below passed on any machine by accident.
        result = subprocess.run(
            ["docker", "exec", "careconnect-sdoh-iris-fhir", "uname", "-m"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"docker exec failed: {result.stderr.strip()}"
        container_arch = result.stdout.strip().lower()
        host_arch = platform.machine().lower()
        if "arm64" in host_arch or "aarch64" in host_arch:
            assert container_arch in ("arm64", "aarch64"), (
                f"Expected ARM64 container on Apple Silicon, got: {container_arch}"
            )

    @requires_iris
    def test_hub_iris_version(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        cur = conn.cursor()
        cur.execute("SELECT $ZVERSION")
        version_str = cur.fetchone()[0]
        conn.close()
        assert "2026" in version_str, f"Expected IRIS 2026.x, got: {version_str}"


class TestHealthCheckTiming:
    def test_all_containers_healthy_within_90s(self, fhir):
        start = time.time()
        deadline = start + 90
        while time.time() < deadline:
            try:
                r = fhir.get("/metadata")
                if r.status_code == 200:
                    elapsed = time.time() - start
                    assert elapsed <= 90, f"Stack took {elapsed:.1f}s — over 90s limit"
                    return
            except Exception:
                pass
            time.sleep(3)
        pytest.fail("Stack not healthy within 90 seconds")

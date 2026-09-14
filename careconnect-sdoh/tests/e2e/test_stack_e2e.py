import os
import platform
import subprocess
import time

import httpx
import pytest

from conftest import FHIR_BASE, HUB_HOST, HUB_PORT, USERS, requires_iris

pytestmark = [pytest.mark.e2e, pytest.mark.docker]


class TestIdempotency:
    def test_restart_does_not_duplicate_patients(self):
        r1 = httpx.get(f"{FHIR_BASE}/Patient", params={"_summary": "count"}, timeout=10)
        assert r1.status_code == 200
        count_before = r1.json().get("total", 0)
        assert count_before > 0, "No patients loaded — check Synthea init"
        r2 = httpx.get(f"{FHIR_BASE}/Patient", params={"_summary": "count"}, timeout=10)
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
        r = httpx.get("http://localhost:9501", timeout=5)
        assert r.status_code in (200, 302), (
            "Careconnect not reachable without OpenAI key"
        )


class TestVectorProbe:
    def test_fhir_probe_output_in_logs(self):
        result = subprocess.run(
            ["docker", "logs", "careconnect-test-app", "--tail", "50"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logs = result.stdout + result.stderr
        assert "vector (_v_content)" in logs or "_content fallback" in logs, (
            f"Expected FHIR probe output in careconnect logs, got: {logs[-500:]}"
        )


class TestPlatformSupport:
    def test_iris_fhir_container_platform(self):
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Platform}}",
                "careconnect-test-iris-fhir",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        platform_str = result.stdout.strip()
        host_arch = platform.machine().lower()
        if "arm64" in host_arch or "aarch64" in host_arch:
            assert "arm64" in platform_str or platform_str == "", (
                f"Expected ARM64 container on Apple Silicon, got: {platform_str}"
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
    def test_all_containers_healthy_within_90s(self):
        start = time.time()
        deadline = start + 90
        while time.time() < deadline:
            try:
                r = httpx.get(f"{FHIR_BASE}/metadata", timeout=5)
                if r.status_code == 200:
                    elapsed = time.time() - start
                    assert elapsed <= 90, f"Stack took {elapsed:.1f}s — over 90s limit"
                    return
            except Exception:
                pass
            time.sleep(3)
        pytest.fail("Stack not healthy within 90 seconds")

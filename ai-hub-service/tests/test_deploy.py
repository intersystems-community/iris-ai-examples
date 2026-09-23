"""Deployment wiring: the manifests and the compose file point at things that exist.

Kubernetes accepts a Service whose selector matches no pod and a URL naming a
Service that is not there; both fail only at the first request. These tests
load each overlay the way kustomize would (resources, components, strategic
merge patches on the one Deployment env they touch) and check the wiring:

* every Service selects a workload, on a port that workload declares;
* every host the service is told to call is a Service in that overlay, on the
  port the URL names;
* the config the service is pointed at is one the image carries;
* files deliberately copied (the MCP config, the shared patch) match their source.

When `kustomize` is on PATH the overlays are also built for real and the two
loaders must agree on what each overlay contains.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml
from conftest import CARECONNECT_SDOH, IMAGE_ROOT, ROOT

K8S = ROOT / "deploy" / "k8s"
OVERLAYS = ["inplace", "sidecar", "sidecar-demo"]
REPO = ROOT.parent


def _docs(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def load(directory: Path) -> list[dict]:
    kust = yaml.safe_load((directory / "kustomization.yaml").read_text())
    objs: list[dict] = []
    for entry in kust.get("resources", []) + kust.get("components", []):
        target = (directory / entry).resolve()
        objs += load(target) if target.is_dir() else _docs(target)
    for gen in kust.get("configMapGenerator", []):
        files = {}
        for f in gen.get("files", []):
            key, _, src = f.partition("=")
            files[key] = (directory / (src or key)).read_text()
        objs.append({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": gen["name"]}, "data": files})
    for patch in kust.get("patches", []):
        path = (directory / patch["path"]).resolve()
        assert directory.resolve() in path.parents, f"{path} is outside {directory}: kustomize refuses it"
        for p in _docs(path):
            _apply(objs, p)
    return objs


def _apply(objs, patch):
    target = find(objs, patch["kind"], patch["metadata"]["name"])
    assert target, f"patch targets missing {patch['kind']}/{patch['metadata']['name']}"
    for pc in patch["spec"]["template"]["spec"]["containers"]:
        tc = next(c for c in target["spec"]["template"]["spec"]["containers"] if c["name"] == pc["name"])
        env = {e["name"]: e for e in tc.get("env", [])}
        env.update({e["name"]: e for e in pc.get("env", [])})
        tc["env"] = list(env.values())


def find(objs, kind, name):
    return next((o for o in objs if o["kind"] == kind and o["metadata"]["name"] == name), None)


def workloads(objs):
    return [o for o in objs if o["kind"] in ("Deployment", "StatefulSet")]


def env_of(objs, name="aihub-service"):
    dep = find(objs, "Deployment", name)
    c = dep["spec"]["template"]["spec"]["containers"][0]
    return {e["name"]: e.get("value") for e in c.get("env", [])}


@pytest.fixture(params=OVERLAYS)
def overlay(request):
    return request.param, load(K8S / "overlays" / request.param)


def test_workload_selectors_match_their_own_pods(overlay):
    _, objs = overlay
    for w in workloads(objs):
        sel = w["spec"]["selector"]["matchLabels"]
        labels = w["spec"]["template"]["metadata"]["labels"]
        assert sel.items() <= labels.items(), w["metadata"]["name"]


def test_every_service_selects_a_workload_on_a_declared_port(overlay):
    name, objs = overlay
    for svc in (o for o in objs if o["kind"] == "Service"):
        if svc["spec"].get("type") == "ExternalName":
            continue
        sel = svc["spec"]["selector"]
        matches = [w for w in workloads(objs)
                   if sel.items() <= w["spec"]["template"]["metadata"]["labels"].items()]
        assert matches, f"{name}: Service {svc['metadata']['name']} selects no workload"
        ports = {p.get("name") for w in matches for c in w["spec"]["template"]["spec"]["containers"]
                 for p in c.get("ports", [])}
        for p in svc["spec"]["ports"]:
            assert p["targetPort"] in ports, f"{name}: {svc['metadata']['name']} -> {p['targetPort']}"


def _service_ports(objs, host):
    svc = find(objs, "Service", host)
    return {p["port"] for p in svc["spec"]["ports"]} if svc else None


def test_every_host_the_service_calls_is_a_service_here(overlay):
    name, objs = overlay
    env = env_of(objs)
    if "AIHUB_MCP_URL" in env:
        u = urlparse(env["AIHUB_MCP_URL"])
        assert _service_ports(objs, u.hostname) and u.port in _service_ports(objs, u.hostname), \
            f"{name}: {env['AIHUB_MCP_URL']} names no Service port in this overlay"
    if "LEGACY_IRIS_HOST" in env:
        ports = _service_ports(objs, env["LEGACY_IRIS_HOST"])
        assert ports and int(env.get("LEGACY_IRIS_PORT", 1972)) in ports, name


def test_the_config_the_service_runs_is_in_the_image_and_matches_the_overlay(overlay):
    name, objs = overlay
    path = env_of(objs)["AIHUB_CONFIG"]
    assert path.startswith(IMAGE_ROOT)
    local = ROOT / path[len(IMAGE_ROOT):]
    assert local.exists(), path
    assert yaml.safe_load(local.read_text())["service"]["mode"] == name.replace("-demo", "")


def test_the_companion_mcp_config_is_careconnects_own():
    ours = (K8S / "components" / "companion" / "mcp-config.toml").read_text()
    theirs = (CARECONNECT_SDOH / "services" / "iris-mcp-sidecar" / "config.toml").read_text()
    assert ours == theirs


def test_the_demo_overlay_shares_the_sidecar_patch():
    a = (K8S / "overlays" / "sidecar" / "aihub-service-env.yaml").read_text()
    b = (K8S / "overlays" / "sidecar-demo" / "aihub-service-env.yaml").read_text()
    assert a == b


def test_the_legacy_demo_calls_the_service_by_its_cluster_name():
    script = (ROOT / "docker" / "legacy-iris" / "iris.script").read_text()
    m = re.search(r'AIHub\.Client\)\.Configure\("([^"]+)",(\d+),', script)
    objs = load(K8S / "overlays" / "sidecar-demo")
    assert m and int(m.group(2)) in _service_ports(objs, m.group(1))


def test_the_service_runs_unprivileged():
    dep = find(load(K8S / "base"), "Deployment", "aihub-service")
    pod = dep["spec"]["template"]["spec"]
    c = pod["containers"][0]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["securityContext"]["allowPrivilegeEscalation"] is False
    assert {"readinessProbe", "livenessProbe"} <= set(c)


@pytest.mark.skipif(not shutil.which("kustomize"), reason="kustomize not on PATH")
@pytest.mark.parametrize("name", OVERLAYS)
def test_kustomize_agrees(name):
    out = subprocess.run(["kustomize", "build", str(K8S / "overlays" / name)],
                         capture_output=True, text=True, check=True).stdout
    real = {(d["kind"], re.sub(r"-[a-z0-9]{10}$", "", d["metadata"]["name"])) for d in yaml.safe_load_all(out) if d}
    ours = {(o["kind"], o["metadata"]["name"]) for o in load(K8S / "overlays" / name)}
    assert real == ours


# -- compose -----------------------------------------------------------------


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_compose_configs_and_builds_exist():
    services = compose()["services"]
    for name, svc in services.items():
        env = svc.get("environment", {})
        if isinstance(env, dict) and "AIHUB_CONFIG" in env:
            assert (ROOT / env["AIHUB_CONFIG"][len(IMAGE_ROOT):]).exists(), name
        build = svc.get("build")
        if build:
            ctx = (ROOT / build["context"]).resolve()
            assert (ctx / build.get("dockerfile", "Dockerfile")).exists(), name


def test_every_profile_publishes_the_service_on_one_port():
    services = compose()["services"]
    for profile in ("offline", "inplace", "sidecar"):
        mine = [s for s in services.values() if profile in s.get("profiles", []) and "AIHUB_CONFIG" in s.get("environment", {})]
        assert len(mine) == 1, profile
        assert mine[0]["ports"] == ["${AIHUB_PORT:-8080}:8080"]


def test_legacy_image_copies_only_files_that_exist():
    dockerfile = (ROOT / "docker" / "legacy-iris" / "Dockerfile").read_text()
    for src in re.findall(r"^COPY\s+(?:--\S+\s+)*(\S+)\s+\S+$", dockerfile, re.M):
        assert (REPO / src).exists(), src


# Community images carry a time-limited licence. The published
# intersystemsdc/irishealth-community:2025.1 (2025.1.0.230.2com) refused to
# start on 2026-09-23 with "Community License expired", so the sidecar demo
# could not build for anyone. A tag goes here once it has been seen to expire.
EXPIRED_COMMUNITY_TAGS = {"2025.1"}


def test_the_legacy_release_is_pinned_once_and_still_starts():
    dockerfile = (ROOT / "docker" / "legacy-iris" / "Dockerfile").read_text()
    compose_text = (ROOT / "docker-compose.yml").read_text()
    env_example = (ROOT / ".env.example").read_text()
    pins = {
        "Dockerfile": re.search(r"^ARG LEGACY_IRIS_VERSION=(\S+)", dockerfile, re.M).group(1),
        "docker-compose.yml": re.search(r"LEGACY_IRIS_VERSION:-([^}]+)\}", compose_text).group(1),
        ".env.example": re.search(r"LEGACY_IRIS_VERSION=(\S+)", env_example).group(1),
    }
    assert len(set(pins.values())) == 1, pins
    assert pins["Dockerfile"] not in EXPIRED_COMMUNITY_TAGS, pins

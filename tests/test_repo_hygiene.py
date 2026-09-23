"""Fit-and-finish guards for the public examples repo.

This repo is published to github.com/intersystems-community/iris-ai-examples.
Every test here encodes something that was measured wrong once: an internal
hostname in a tracked file, a personal filesystem path, a doc string the code
contradicts, a port a reader could not override. They are cheap, they run
without Docker or an API key, and they fail loudly rather than letting the
same class of defect back in.

    pytest tests/
"""

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Text-ish files worth scanning. Binary and vendored trees are skipped.
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".sh",
    ".cls",
    ".json",
    ".ipynb",
    ".script",
    ".example",
    ".txt",
    ".cfg",
    ".xml",
}

SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".speckit"}


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p]


def text_files():
    here = Path(__file__).resolve()
    for path in tracked_files():
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # The guards quote the very strings they forbid, so the file that holds them
        # would fail its own tests the moment it was tracked. Measured: it did.
        if path.resolve() == here:
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name != "Dockerfile":
            continue
        if not path.is_file():
            continue
        yield path


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def offenders(pattern, files=None):
    """Every (relative path, line number, line) matching pattern."""
    rx = re.compile(pattern)
    hits = []
    for path in files if files is not None else text_files():
        for n, line in enumerate(read(path).splitlines(), 1):
            if rx.search(line):
                hits.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:120]}")
    return hits


# --------------------------------------------------------------------------
# Nothing internal, nothing personal
# --------------------------------------------------------------------------


def test_no_internal_hostnames_are_tracked():
    """An internal registry or wiki hostname in a public repo is a disclosure."""
    hits = offenders(r"\biscinternal\.com\b|\bdpgenai\d\b")
    assert not hits, "internal hostnames in tracked files:\n" + "\n".join(hits)


def test_no_personal_vault_or_home_paths_are_tracked():
    """Absolute paths off one laptop cannot work for a reader, and they name a person."""
    hits = offenders(r"/Users/|TomNotes|iCloud~md~obsidian")
    assert not hits, "machine-specific paths in tracked files:\n" + "\n".join(hits)


def test_no_workspace_relative_paths_are_tracked():
    """`~/ws/<project>` is this maintainer's monorepo layout, not the reader's."""
    hits = offenders(r"~/ws/")
    assert not hits, "monorepo paths in tracked files:\n" + "\n".join(hits)


def test_no_other_projects_are_named():
    """The container/port inventory of unrelated projects does not belong here."""
    hits = offenders(r"\blos-iris\b|\bopsreview-iris\b|\baihub-iris-\d+\b|\bposos-iris\b")
    assert not hits, "unrelated project containers named:\n" + "\n".join(hits)


# --------------------------------------------------------------------------
# The repo says what it is
# --------------------------------------------------------------------------


def test_license_is_mit_and_owned_by_intersystems():
    license_file = REPO / "LICENSE"
    assert license_file.exists(), "public repo has no LICENSE"
    body = read(license_file)
    assert "MIT License" in body
    assert "Copyright (c) 2026 InterSystems Corporation" in body
    assert "Permission is hereby granted, free of charge" in body


def test_specs_are_not_tracked_in_the_public_repo():
    """Internal spec artifacts stay in the private planning repo."""
    tracked = {str(p.relative_to(REPO)) for p in tracked_files()}
    leaked = sorted(p for p in tracked if "/specs/" in p or p.startswith("specs/"))
    assert not leaked, "internal specs tracked publicly:\n" + "\n".join(leaked)


def test_the_superseded_minimal_docker_tree_is_gone():
    """careconnect-sdoh/docker/ was an earlier single-container cut of the same demo.

    It had broken COPY paths and its own drifting copy of the compose file, and
    the top-level stack replaced it.
    """
    assert not (REPO / "careconnect-sdoh" / "docker").exists()


def test_the_zpm_manifest_is_declared_once():
    """Two byte-identical 1.4 MB manifests is a fork waiting to happen."""
    manifests = sorted(
        str(p.relative_to(REPO)) for p in tracked_files() if p.name == "zpm.xml"
    )
    assert len(manifests) <= 1, "duplicate zpm.xml:\n" + "\n".join(manifests)


# --------------------------------------------------------------------------
# careconnect-python is the Python example
# --------------------------------------------------------------------------


def test_careconnect_python_ships_only_its_data_classes():
    """The example's claim is that the agent and its tools are pure Python.

    The persistent class and its demo loader stay because the Python tools read
    them over SQL. Everything else -- the toolset, the MCP service, the
    Interoperability production -- belonged to careconnect-sdoh and made the
    "no ObjectScript" claim false.
    """
    root = REPO / "careconnect-python" / "src" / "CareConnect"
    shipped = sorted(
        str(p.relative_to(root)) for p in tracked_files() if root in p.parents
    )
    assert shipped == ["Patient.cls", "Setup/DemoData.cls"], shipped


def test_careconnect_python_startup_compiles_only_what_it_ships():
    """A build-time script that compiles a deleted class fails the image build."""
    docker = REPO / "careconnect-python" / "docker"
    scripts = [p for p in docker.iterdir() if p.suffix in {".script", ".sh"}]
    assert scripts, "no startup script found"
    for script in scripts:
        name, body = script.name, read(script)
        for gone in (
            "CareConnect.Tools.SDoHToolSet",
            "CareConnect.MCP.Service",
            "CareConnect.Production",
            "CareConnect.Setup.MCPSetup",
            "CareConnect.Message.",
            "CareConnect.Service.",
            "CareConnect.Process.",
            "CareConnect.Operation.",
        ):
            assert gone not in body, f"{name} still references {gone}"


# --------------------------------------------------------------------------
# The SDoH rule scores six domains
# --------------------------------------------------------------------------

# careconnect-sdoh's ObjectScript scorer has six domains -- the five USDHHS
# ones plus transportation access -- and URGENT needs 5 of them. Several strings
# said five and one said 4+, including the XData <Description> the model reads
# at tool-selection time.
#
# Scoped to careconnect-sdoh on purpose: careconnect-python ships its own
# five-domain Python scorer (DOMAIN_KEYWORDS has five keys, URGENT at >= 4), so
# "five domains" and "4+" are true there and must stay.
#
# "six SDoH domains (five USDHHS plus transportation access)" is the accurate
# phrasing and appears verbatim in the XData description and its mirror, so the
# bare-"five USDHHS" pattern has to let that one construction through. The
# lookahead stops at "plus" rather than "plus transportation" because black
# splits the mirror's copy of the string right after "five USDHHS plus ".
STALE_DOMAIN_CLAIMS = [
    r"\ball five USDHHS\b",
    r"\ball 5 USDHHS\b",
    r"\bfive USDHHS\b(?! plus)",
    r"\bfive SDoH domains\b",
    r"\bfive social determinant",
    r"/5 domains\b",
    r"\(5 domains\b",
    r"\b4\+ domains\b",
]


def test_the_sdoh_rule_is_documented_as_six_domains():
    sdoh = [p for p in text_files() if p.relative_to(REPO).parts[0] == "careconnect-sdoh"]
    hits = []
    for pattern in STALE_DOMAIN_CLAIMS:
        hits += offenders(pattern, files=sdoh)
    assert not hits, "stale five-domain claims:\n" + "\n".join(sorted(hits))


def test_the_toolset_and_its_mirror_agree_on_the_description():
    """tools_local.py mirrors the XData description on purpose: the model reads it."""
    cls = read(
        REPO
        / "careconnect-sdoh"
        / "src"
        / "CareConnect"
        / "Tools"
        / "SDoHToolSet.cls"
    )
    mirror = read(
        REPO / "careconnect-sdoh" / "evals" / "careconnect_evals" / "tools_local.py"
    )
    m = re.search(r"Score a patient[^<\"]*", cls)
    assert m, "AssessSDoHRisk description not found in the XData"
    description = m.group(0).strip()
    # black splits the mirror's copy across two adjacent string literals; join
    # them back up so the comparison is against the value, not the source.
    mirror = re.sub(r'"\s*\n\s*"', "", mirror)
    assert description in mirror, (
        "the mirror's TOOL_SCHEMAS description has drifted from the XData:\n"
        f"  .cls: {description}"
    )


def test_the_eval_mirror_covers_search_clinical_notes():
    """SearchClinicalNotes is the one shipped tool the mirror could port without a graph."""
    mirror = read(
        REPO / "careconnect-sdoh" / "evals" / "careconnect_evals" / "tools_local.py"
    )
    assert "def SearchClinicalNotes" in mirror


# --------------------------------------------------------------------------
# A reader can run it
# --------------------------------------------------------------------------


def compose_files():
    return [p for p in tracked_files() if p.name.startswith("docker-compose")]


def test_every_published_port_is_overridable():
    """A hardcoded host port collides with whatever the reader already runs."""
    bad = []
    for path in compose_files():
        for n, line in enumerate(read(path).splitlines(), 1):
            m = re.match(r'\s*-\s*"(?P<host>[^:"]+):(?P<container>\d+)"\s*$', line)
            if m and not m.group("host").startswith("${"):
                bad.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert not bad, "hardcoded host ports:\n" + "\n".join(bad)


def test_one_image_variable_name_across_the_repo():
    """IRIS_HUB_IMAGE, AIHUB_IRIS_IMAGE, IMAGE and a hardcoded tag were four idioms."""
    hits = offenders(r"\bIRIS_HUB_IMAGE\b|\bAIHUB_IRIS_IMAGE\b")
    assert not hits, "superseded image variable names:\n" + "\n".join(hits)


def test_the_image_variable_always_carries_a_default():
    """`${IRIS_IMAGE}` with no default fails as an empty string, which reads as a
    Docker error rather than a missing-configuration message."""
    bad = offenders(r"\$\{IRIS_IMAGE\}")
    assert not bad, "IRIS_IMAGE used without a default:\n" + "\n".join(bad)


def test_container_names_share_one_prefix_scheme():
    """Every container is named after the example directory it belongs to."""
    prefixes = {
        "ai-hub": "ai-hub-",
        "ai-hub-service": "ai-hub-service-",
        "careconnect-python": "careconnect-python-",
        "careconnect-sdoh": "careconnect-sdoh-",
        "kg-ticket-resolver": "kg-ticket-resolver-",
    }
    bad = []
    for path in compose_files():
        example = path.relative_to(REPO).parts[0]
        want = prefixes.get(example)
        if not want:
            continue
        for n, line in enumerate(read(path).splitlines(), 1):
            m = re.match(r"\s*container_name:\s*(?P<name>.+?)\s*$", line)
            if not m:
                continue
            name = m.group("name")
            resolved = re.sub(r"^\$\{[A-Z_]+:-(.*)\}$", r"\1", name)
            if not resolved.startswith(want):
                bad.append(
                    f"{path.relative_to(REPO)}:{n}: {resolved} (want {want}*)"
                )
    assert not bad, "container names off the scheme:\n" + "\n".join(bad)


def test_no_env_example_sets_an_image_variable_compose_never_reads():
    """`IMAGE=` in a .env.example is a variable nothing resolves.

    careconnect-python shipped `IMAGE=irishealth-community:2026.2.0AI.162.0`
    while its compose file read `${IRIS_IMAGE:-...}`, so a reader who edited the
    line they were told to edit got the public community image anyway.
    """
    bad = []
    for path in tracked_files():
        if path.name != ".env.example":
            continue
        for n, line in enumerate(read(path).splitlines(), 1):
            m = re.match(r"\s*#?\s*(?P<var>[A-Z][A-Z0-9_]*)\s*=", line)
            if m and m.group("var").endswith("IMAGE") and m.group("var") != "IRIS_IMAGE":
                bad.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert not bad, "image variables no compose file reads:\n" + "\n".join(bad)


def test_the_kg_env_example_matches_its_compose_port():
    """A copied .env.example that points at nothing is a first-run failure."""
    env = read(REPO / "kg-ticket-resolver" / ".env.example")
    compose = read(REPO / "kg-ticket-resolver" / "docker" / "docker-compose.yml")
    m = re.search(r"^IRIS_PORT=(\d+)", env, re.M)
    assert m, "kg .env.example does not set IRIS_PORT"
    default = re.search(r'"\$\{IRIS_PORT:-(\d+)\}:1972"', compose)
    assert default, "kg compose does not default IRIS_PORT"
    assert m.group(1) == default.group(1), (
        f".env.example says {m.group(1)}, compose defaults to {default.group(1)}"
    )


def test_the_notebook_does_not_hardcode_a_container_name():
    """The notebook ran against a container this repo has never defined."""
    nb = REPO / "kg-ticket-resolver" / "notebooks" / "planetcare_clustering_demo.ipynb"
    if not nb.exists():
        pytest.skip("notebook not present")
        return
    cells = json.loads(read(nb))["cells"]
    source = "".join("".join(c.get("source", [])) for c in cells)
    assert "kg-iris" not in source, "notebook still defaults to the 'kg-iris' container"


# --------------------------------------------------------------------------
# The test suite a reader runs is the one that was written
# --------------------------------------------------------------------------

# Four measured ways a test can look present and never run, or run and never
# pass. All four were live in this repo at once, and none of them shows up as a
# failure in `pytest` -- which is the point of guarding them from outside.


def python_test_modules():
    return [
        p
        for p in tracked_files()
        if p.suffix == ".py"
        and p.name.startswith("test_")
        and p.resolve() != Path(__file__).resolve()
    ]


def test_every_tracked_test_module_is_reachable_from_a_testpaths_root():
    """A test module outside `testpaths` is never collected and never fails.

    careconnect-sdoh/src/CareConnect/phi_guardian/tests/ held two modules that
    `pytest` in that directory has never once collected, one of which does not
    even import.
    """
    unreachable = []
    for ini in (p for p in tracked_files() if p.name == "pytest.ini"):
        root = ini.parent
        m = re.search(r"^testpaths\s*=\s*(?P<paths>.+)$", read(ini), re.M)
        if not m:
            continue
        roots = [(root / t).resolve() for t in m.group("paths").split()]
        for path in python_test_modules():
            if root not in path.parents:
                continue
            if not any(r == path.resolve() or r in path.resolve().parents for r in roots):
                unreachable.append(
                    f"{path.relative_to(REPO)} (testpaths: {m.group('paths')})"
                )
    assert not unreachable, "test modules pytest never collects:\n" + "\n".join(
        sorted(unreachable)
    )


def test_no_test_module_imports_a_package_this_repo_does_not_ship():
    """`packages.phi_guardian...` is the pre-port layout of a different project.

    The import raises at collection time, so it takes its whole module with it
    -- and because the module sat outside testpaths, nothing ever said so.
    """
    hits = offenders(r"^\s*(?:from|import)\s+packages\.", files=python_test_modules())
    assert not hits, "imports of a package that does not exist here:\n" + "\n".join(hits)


def test_the_docker_fixture_reads_markers_it_can_actually_see():
    """`item.own_markers` does not contain module-level `pytestmark`.

    Measured on this repo: for tests/e2e/test_stack_smoke.py, own_markers is
    ['skipif'] while iter_markers() is ['docker', 'skipif', 'smoke']. Every e2e
    module here declares its markers through module-level pytestmark, so a
    fixture that gates on own_markers always concludes no Docker is needed and
    silently skips bringing the stack up.
    """
    conftests = [p for p in tracked_files() if p.name == "conftest.py"]
    assert conftests, "no conftest.py tracked"
    hits = []
    for path in conftests:
        for node in ast.walk(ast.parse(read(path))):
            # Attribute reads, not a grep: the comment above the fixed line names
            # own_markers to say why it is wrong, and that is not a use of it.
            if isinstance(node, ast.Attribute) and node.attr == "own_markers":
                hits.append(f"{path.relative_to(REPO)}:{node.lineno}: {ast.unparse(node)}")
    assert not hits, (
        "conftest gates on own_markers, which cannot see module-level "
        "pytestmark -- use iter_markers():\n" + "\n".join(hits)
    )


def _documentation_or_env_default(tree):
    """Ids of string nodes that are prose or a reader-overridable default.

    Two legitimate cases, and a line-based grep flags both: a module docstring
    that prints the URL of a container this compose file does not define
    (ai-hub's live-IdP module, whose container comes from a setup script), and a
    run recipe quoted in prose. `os.environ.get(..., default)` is the override
    point itself, so a literal inside it is configuration, not a hardcoded host.
    """
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skip.add(id(node.value))
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name.endswith("environ.get") or name.endswith("getenv"):
                for arg in node.args:
                    for sub in ast.walk(arg):
                        skip.add(id(sub))
    return skip


def _documentation(tree):
    """Ids of string nodes that are prose, and nothing else.

    Container names get only this exemption, not the env-default one: compose
    fixes `container_name` outright here, so a default is as wrong as a literal.
    """
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }


def _asserted_ports(path):
    """(line, port) for every host port a test module connects to outright."""
    tree = ast.parse(read(path))
    skip = _documentation_or_env_default(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # _port_open("localhost", 55773) / connect((HUB_HOST, 1973))
            addressed = any(
                (isinstance(a, ast.Constant) and a.value == "localhost")
                or (
                    isinstance(a, (ast.Name, ast.Attribute))
                    and "HOST" in ast.unparse(a).upper()
                )
                for a in node.args
            )
            if addressed:
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, int)
                        and not isinstance(arg.value, bool)
                        and id(arg) not in skip
                    ):
                        found.append((arg.lineno, str(arg.value)))
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
        ):
            for m in re.finditer(r"localhost:(?P<port>\d+)", node.value):
                found.append((node.lineno, m.group("port")))
    return found


def test_no_test_hardcodes_a_host_port_its_own_compose_never_publishes():
    """Ports 55773/55501/55888/9501 are the private planning repo's test stack.

    They survived the port into a suite whose compose file publishes 52774,
    1973, 8888, 8501, 8889 and friends, so four assertions could not pass on any
    machine running this repo's stack. Parsed rather than grepped, because the
    two prose mentions of a port in this repo are both correct.
    """
    bad = []
    for example in sorted({p.relative_to(REPO).parts[0] for p in python_test_modules()}):
        root = REPO / example
        composes = [p for p in compose_files() if root in p.parents]
        if not composes:
            continue
        published = set()
        for path in composes:
            body = read(path)
            published |= set(re.findall(r'"\$\{[A-Z_]+:-(\d+)\}:\d+"', body))
            published |= set(re.findall(r'"(\d+):\d+"', body))
        for path in python_test_modules():
            if root not in path.parents:
                continue
            for lineno, port in _asserted_ports(path):
                if port in published or int(port) < 1024:
                    continue
                bad.append(
                    f"{path.relative_to(REPO)}:{lineno}: {port} "
                    f"(compose publishes {', '.join(sorted(published))})"
                )
    assert not bad, (
        "tests assert on host ports this example's compose never publishes:\n"
        + "\n".join(bad)
    )


def test_no_test_names_a_container_its_own_compose_never_defines():
    """`docker logs careconnect-test-app` names the private repo's test stack.

    A wrong container name fails as "No such container", which reads as a stack
    that did not come up rather than a test looking for the wrong thing. Names
    accepted here are the `container_name:` values plus the network aliases,
    because the aliases are deliberate and documented in the compose file.
    """
    bad = []
    for example in sorted({p.relative_to(REPO).parts[0] for p in python_test_modules()}):
        root = REPO / example
        composes = [p for p in compose_files() if root in p.parents]
        if not composes:
            continue
        defined = set()
        for path in composes:
            body = read(path)
            for name in re.findall(r"^\s*container_name:\s*(.+?)\s*$", body, re.M):
                defined.add(re.sub(r"^\$\{[A-Z_]+:-(.*)\}$", r"\1", name))
            for name in re.findall(r"^\s*-\s*(careconnect-[a-z0-9-]+)\s*$", body, re.M):
                defined.add(name)
        for path in python_test_modules():
            if root not in path.parents:
                continue
            tree = ast.parse(read(path))
            skip = _documentation(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if id(node) in skip:
                    continue
                for name in re.findall(
                    r"\b(?:careconnect|ai-hub|kg-ticket-resolver)-[a-z0-9-]+", node.value
                ):
                    if name not in defined:
                        bad.append(
                            f"{path.relative_to(REPO)}:{node.lineno}: {name} "
                            f"(compose defines {', '.join(sorted(defined))})"
                        )
    assert not bad, "tests name containers this compose never defines:\n" + "\n".join(
        sorted(set(bad))
    )


def test_embedded_python_detection_does_not_trust_a_pip_install():
    """`iris_ep.py` next to the `iris` package ships with intersystems-irispython.

    Measured on a laptop with only the pip wheel installed: the file is present,
    so a check for it reports an embedded context, `iris.cls(...)` hands back a
    unittest.mock.MagicMock, and 27 ai-hub tests fail on assertions about a
    MagicMock instead of skipping. Detect the runtime, not the wheel.
    """
    hits = []
    for path in python_test_modules():
        tree = ast.parse(read(path))
        prose = _documentation(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "iris_ep" in node.value
                and id(node) not in prose
            ):
                hits.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.value}")
    assert not hits, (
        "embedded-Python detection keyed on a file the pip wheel also ships:\n"
        + "\n".join(hits)
    )


def test_no_conftest_stubs_a_module_for_the_whole_process():
    """`sys.modules["iris"] = MagicMock()` at import time is not scoped to a directory.

    Measured with the full stack up: careconnect-sdoh/tests/unit/conftest.py does
    that assignment at module import, pytest imports it while collecting, and
    every e2e test that does `import iris` inside its body then gets the mock.
    Five e2e tests asserted about MagicMocks against a live IRIS -- including one
    expecting an exception on bad credentials, which a mock never raises. Stub
    only what the environment does not already provide.
    """
    hits = []
    for path in (p for p in tracked_files() if p.name == "conftest.py"):
        for node in ast.parse(read(path)).body:  # module level only
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and ast.unparse(target.value).endswith("sys.modules")
                ):
                    hits.append(
                        f"{path.relative_to(REPO)}:{node.lineno}: {ast.unparse(node)[:80]}"
                    )
    assert not hits, (
        "conftest replaces a module process-wide at import time:\n" + "\n".join(hits)
    )


def test_no_test_imports_a_dotted_path_that_does_not_exist_on_disk():
    """`from services.iris_fhir.init...` cannot resolve: the directory is `iris-fhir`.

    A hyphen is not importable, so that line raises ModuleNotFoundError at the
    moment the test runs -- which reads as a missing dependency rather than a
    path that was never right.
    """
    bad = []
    for path in python_test_modules():
        example = REPO / path.relative_to(REPO).parts[0]
        for node in ast.walk(ast.parse(read(path))):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            head = node.module.split(".")[0]
            if not (example / head).is_dir():
                continue  # not a path rooted in this example's own tree
            target = example.joinpath(*node.module.split("."))
            if not (target.is_dir() or target.with_suffix(".py").is_file()):
                bad.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.module}")
    assert not bad, "tests import module paths that do not exist:\n" + "\n".join(bad)


def test_no_test_calls_an_authenticated_service_without_the_fixture():
    """A bare `httpx.get(f"{FHIR_BASE}/Patient")` sends no credentials.

    The `fhir` fixture exists precisely because this FHIR server answers 401 on
    everything except /metadata. Measured against the live stack: four tests that
    reached past the fixture failed on 401 while the one /metadata call passed,
    which reads as a half-loaded server rather than a missing Authorization
    header.
    """
    bad = []
    for path in python_test_modules():
        tree = ast.parse(read(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).startswith("httpx."):
                continue
            if any(kw.arg == "auth" for kw in node.keywords):
                continue
            if "FHIR_BASE" in ast.unparse(node):
                bad.append(f"{path.relative_to(REPO)}:{node.lineno}: {ast.unparse(node)[:90]}")
    assert not bad, (
        "unauthenticated FHIR calls outside the fixture:\n" + "\n".join(bad)
    )


def test_no_test_passes_a_global_name_first_to_the_native_set():
    """`IRIS.set()` takes the VALUE first: set(value, globalName, subscripts...).

    `iris_obj.set("^CareConnect.LastPoll", "2026-01-01T00:00:00Z")` reads naturally
    and is wrong — IRIS tries to use the timestamp as a global name and raises
    RuntimeError <SYNTAX>, which names neither the argument order nor the global.
    Measured against the live stack: all three call sites were reversed. `get()`
    really does take the global name first, so the two are not symmetric.
    """
    bad = []
    for path in python_test_modules():
        for node in ast.walk(ast.parse(read(path))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "set"):
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and str(first.value).startswith("^"):
                bad.append(
                    f"{path.relative_to(REPO)}:{node.lineno}: {ast.unparse(node)[:80]}"
                )
    assert not bad, (
        "IRIS.set() called with the global name first; value comes first:\n"
        + "\n".join(bad)
    )


# --------------------------------------------------------------------------
# Every doc is reachable, and every link resolves
# --------------------------------------------------------------------------

# A reader arrives at the root README and clicks. Anything no README points at
# is a doc only `git ls-files` can find -- measured here once at 933 lines,
# including all three DEMO.md walkthroughs, which are the first thing a reader
# wants after the stack is up.

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(\s*(?P<target>[^)\s]+)")

# Docs a reader is not expected to click their way to. AGENTS.md and CLAUDE.md
# are addressed to coding agents, which read them by filename convention;
# SKILL.md is loaded by name through the skill system; the root README is the
# entry point itself; and data/ holds the seeded wiki the kg example mines, which
# is demo content rather than documentation.
UNLINKED_BY_DESIGN = {"AGENTS.md", "CLAUDE.md", "SKILL.md"}


def markdown_files():
    return [p for p in tracked_files() if p.suffix == ".md" and p.is_file()]


def markdown_links(path):
    """(line number, raw target) for every relative link in one file.

    External URLs, mailto: and bare anchors address nothing on disk, so they are
    not this guard's business.
    """
    for n, line in enumerate(read(path).splitlines(), 1):
        for m in MARKDOWN_LINK.finditer(line):
            target = m.group("target")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            yield n, target


def link_target(path, target):
    """Where a relative link lands, with the fragment and trailing slash gone."""
    return (path.parent / target.split("#", 1)[0].rstrip("/")).resolve()


def test_every_relative_doc_link_resolves():
    """A dead relative link renders as a live link and 404s on GitHub.

    Nothing in this repo checked them, so a file move was free to break every
    reference to it without failing a test or a build.
    """
    bad = []
    for path in markdown_files():
        for lineno, target in markdown_links(path):
            resolved = link_target(path, target)
            if not resolved.exists():
                bad.append(f"{path.relative_to(REPO)}:{lineno}: {target}")
    assert not bad, "relative links that resolve to nothing:\n" + "\n".join(bad)


def test_every_tracked_doc_is_reachable_by_clicking():
    """Each .md is linked from another .md, directly or through its directory.

    A link to `./careconnect-sdoh/` counts as reaching that directory's README,
    because that is what GitHub renders there. Measured before the root README
    grew a docs index: careconnect-sdoh/DEMO.md, careconnect-python/DEMO.md,
    kg-ticket-resolver/DEMO.md, evals/PRESENTATION.md and the seeded wiki were
    all unreachable, and AGENTS.md named two of them in table cells as bare text
    rather than links -- so agents found them and readers could not.
    """
    linked = set()
    for path in markdown_files():
        for _, target in markdown_links(path):
            resolved = link_target(path, target)
            linked.add(resolved)
            if resolved.is_dir():
                linked.add((resolved / "README.md").resolve())

    orphans = sorted(
        str(p.relative_to(REPO))
        for p in markdown_files()
        if p.resolve() not in linked
        and p.name not in UNLINKED_BY_DESIGN
        and p.resolve() != (REPO / "README.md").resolve()
        and "data" not in p.relative_to(REPO).parts
    )
    assert not orphans, (
        "docs no other doc links to -- add them to the root README index:\n"
        + "\n".join(orphans)
    )

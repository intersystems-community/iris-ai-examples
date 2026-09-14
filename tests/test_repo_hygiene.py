"""Fit-and-finish guards for the public examples repo.

This repo is published to github.com/intersystems-community/iris-ai-examples.
Every test here encodes something that was measured wrong once: an internal
hostname in a tracked file, a personal filesystem path, a doc string the code
contradicts, a port a reader could not override. They are cheap, they run
without Docker or an API key, and they fail loudly rather than letting the
same class of defect back in.

    pytest tests/
"""

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

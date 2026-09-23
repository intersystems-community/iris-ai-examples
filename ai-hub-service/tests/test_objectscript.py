"""The ObjectScript side, checked without an IRIS.

The AIHub.* classes are the half of the contract that runs inside customer
IRIS instances, often old ones. Nothing here can compile them, so these tests
pin what can be pinned from source:

* they use nothing a pre-AI-Hub IRIS lacks;
* every URL they call is a route the service serves, with the JSON fields they
  read present in what the service returns;
* every classmethod, table and column the sidecar config binds to exists in a
  class this repo ships, and every tool it sends to the companion is one
  SDoHToolSet's XData declares.

Compilation on a real IRIS is the step these cannot replace; the design doc
records the releases it was measured on and the one defect it found.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import CARECONNECT_SDOH, EXAMPLES, ROOT

from aihub_service.app import create_app
from aihub_service.config import load_config
from aihub_service.runs import Run

CLS_ROOT = ROOT / "objectscript"
SHIPPED = sorted(CLS_ROOT.rglob("*.cls"))
REPO = ROOT.parent
CARECONNECT_SRC = CARECONNECT_SDOH / "src"
TOOLSET = CARECONNECT_SRC / "CareConnect" / "Tools" / "SDoHToolSet.cls"


def body(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code(path: Path) -> str:
    """The class without its /// comments, which quote things on purpose."""
    return "\n".join(l for l in body(path).splitlines() if not l.lstrip().startswith("///"))


def test_the_wrapper_classes_ship():
    names = {str(p.relative_to(CLS_ROOT)) for p in SHIPPED}
    assert names == {
        "AIHub/Client.cls",
        "AIHub/SQL.cls",
        "AIHub/Legacy/Interop.cls",
        "AIHub/Interop/AgentOperation.cls",
        "AIHub/Interop/AgentRequest.cls",
        "AIHub/Interop/AgentResponse.cls",
        "AIHub/Interop/RunStatusRequest.cls",
    }


# Each is a real reason a class fails to compile or run on an older IRIS.
NOT_ON_LEGACY = {
    r"%AI\.": "AI Hub classes exist only on 2026.2.0AI+",
    r"\[\s*Language\s*=\s*python": "embedded Python arrived in 2022.1 and is often disabled",
    r"%JSON\.Adaptor": "not on older versions, and would have to be inherited by app classes",
    r"%Net\.URLParser\)\.Decompose": "newer than the Parse() it replaced",
    r"\bReturn\b": "keep to Quit, the idiom every version and this repo share",
}


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_wrappers_are_version_neutral(path):
    hits = [why for rx, why in NOT_ON_LEGACY.items() if re.search(rx, code(path))]
    assert not hits, f"{path.name}: " + "; ".join(hits)


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_class_name_matches_its_path_and_braces_balance(path):
    want = ".".join(path.relative_to(CLS_ROOT).with_suffix("").parts)
    m = re.search(r"^Class\s+([\w.]+)", body(path), re.M)
    assert m and m.group(1) == want
    text = re.sub(r'"[^"\n]*"', '""', code(path))  # braces inside strings do not count
    assert text.count("{") == text.count("}"), f"{path.name}: unbalanced braces"


def test_no_quit_with_an_argument_inside_a_try_block():
    """`Quit value` inside Try is a compile error; argumentless Quit leaves the block."""
    for path in SHIPPED:
        depth, in_try = 0, []
        for n, line in enumerate(code(path).splitlines(), 1):
            if re.match(r"\s*Try\s*\{", line):
                in_try.append(depth)
            depth += line.count("{") - line.count("}")
            while in_try and depth <= in_try[-1]:
                in_try.pop()
            if in_try and re.search(r"\bQuit\s+[^:\s]", line) and not re.search(r"\bQuit\s*$", line):
                pytest.fail(f"{path.name}:{n}: argumented Quit inside Try: {line.strip()}")


# A postconditional ends at its first space, so `Continue:a '= b` leaves `'= b`
# where the compiler wants end of line (#1012 on 2024.1 and 2025.1). Parenthesize.
POSTCONDITIONAL_WITH_A_SPACE = re.compile(
    r"\b(?:Continue|Quit|Set|Do|Write|Kill|Throw|Goto|Lock|Merge|Hang|Xecute)\s*:"
    r"(?!\()\S+\s+(?:'?[=<>\[\]]|&&?|!|_|\|\|)"
)


def test_no_postconditional_holds_an_unparenthesized_space():
    for path in SHIPPED:
        for n, line in enumerate(body(path).splitlines(), 1):
            if line.lstrip().startswith("///"):
                continue
            if POSTCONDITIONAL_WITH_A_SPACE.search(re.sub(r'"[^"\n]*"', '""', line)):
                pytest.fail(f"{path.name}:{n}: parenthesize the postconditional: {line.strip()}")


# -- the client calls routes that exist --------------------------------------


def _routes():
    app = create_app(EXAMPLES / "offline.yaml")
    return {(m, r.path) for r in app.routes for m in getattr(r, "methods", ())}


CALLS = re.compile(r'Call\("(?P<m>GET|POST)",\s*"(?P<p>/v1/[^"]*)"(?P<rest>[^\n]*)')


def _normalize(template: str, rest: str) -> str:
    # "/v1/agents/"_..Segment(agent)_"/runs"  ->  /v1/agents/{}/runs
    joined = template + "".join(re.findall(r'_"(/[^"]*)"', rest.split(",")[0]))
    return re.sub(r"/(?=/|$)", "/{}", joined) if "_.." in rest.split(",")[0] else joined


def test_client_paths_are_routes_the_service_serves():
    served = {(m, re.sub(r"\{[^}]+\}", "{}", p)) for m, p in _routes()}
    used = []
    for m in CALLS.finditer(code(CLS_ROOT / "AIHub" / "Client.cls")):
        used.append((m.group("m"), _normalize(m.group("p").split("?")[0], m.group("rest"))))
    op = code(CLS_ROOT / "AIHub" / "Interop" / "AgentOperation.cls")
    used += [("POST", "/v1/agents/{}/runs"), ("GET", "/v1/runs/{}")]
    assert 'Set path = "/v1/agents/"_' in op and '"/v1/runs/"_' in op
    assert len(used) >= 6
    missing = [u for u in used if u not in served]
    assert not missing, f"the ObjectScript calls routes the service does not serve: {missing}"


def test_the_json_fields_the_wrappers_read_are_ones_a_run_returns():
    public = set(Run(agent="a", input="", context={}, principal="p").public())
    read = set()
    for path in (CLS_ROOT / "AIHub" / "Client.cls", CLS_ROOT / "AIHub" / "Interop" / "AgentOperation.cls"):
        read |= set(re.findall(r"\brun\.(\w+)\b", code(path)))
        read |= set(re.findall(r'run\.%Get\("(\w+)"\)', code(path)))
    read -= {"detail"}  # the error body, not a run
    read -= {"%Get"}
    assert read and read <= public, f"fields read but never returned: {sorted(read - public)}"


# -- the sidecar binds to things that exist ----------------------------------


def _sidecar_tools():
    return {t["name"]: t for t in load_config(EXAMPLES / "sidecar.yaml", environ={}).tools}


def _bindings(tool):
    b = tool.get("binding", {})
    return b.get("cases", [b]) if b else []


def _classmethods(path: Path) -> dict[str, int]:
    """name -> number of formal parameters."""
    out = {}
    for m in re.finditer(r"^ClassMethod\s+(\w+)\(([^)]*)\)", body(path), re.M):
        params = [p for p in m.group(2).split(",") if p.strip()]
        out[m.group(1)] = len(params)
    return out


def test_every_classmethod_the_sidecar_calls_exists_with_room_for_its_args():
    for tool in _sidecar_tools().values():
        for b in _bindings(tool):
            if "classmethod" not in b:
                continue
            cls, _, method = b["classmethod"].rpartition(".")
            path = CLS_ROOT.joinpath(*cls.split(".")).with_suffix(".cls")
            assert path.exists(), f"{tool['name']}: {cls} is not shipped"
            arity = _classmethods(path)
            assert method in arity, f"{tool['name']}: {cls} has no {method}"
            assert len(b.get("args", [])) <= arity[method], f"{tool['name']}: too many args for {method}"


def test_every_class_and_column_the_sidecar_sql_names_exists():
    patient_cols = set(re.findall(r"^Property\s+(\w+)", body(CARECONNECT_SRC / "CareConnect" / "Patient.cls"), re.M))
    for tool in _sidecar_tools().values():
        for b in _bindings(tool):
            sql = b.get("sql")
            if not sql or "CareConnect.Patient" not in sql:
                continue
            select = re.search(r"SELECT\s+(.*?)\s+FROM", sql, re.S).group(1)
            cols = {c.strip() for c in select.split(",")}
            assert cols <= patient_cols, f"{tool['name']}: {sorted(cols - patient_cols)} not in Patient.cls"


def test_the_legacy_dispatch_targets_are_real_careconnect_classes():
    for tool in _sidecar_tools().values():
        for b in _bindings(tool):
            if b.get("classmethod") != "AIHub.Legacy.Interop.Dispatch":
                continue
            service, request = b["args"][:2]
            for cls in (service, request):
                assert CARECONNECT_SRC.joinpath(*cls.split(".")).with_suffix(".cls").exists(), cls
            fields = set(b["args"][2]["json"])
            props = set(re.findall(r"^Property\s+(\w+)", body(CARECONNECT_SRC.joinpath(*request.split(".")).with_suffix(".cls")), re.M))
            assert fields <= props, f"{request} lacks {sorted(fields - props)}"


def test_the_legacy_side_of_careconnect_needs_no_ai_hub():
    """What the sidecar's legacy instance loads must compile without %AI."""
    legacy_classes = ["Patient", "Setup/DemoData", "Production", "Message/FollowUpRequest",
                      "Message/FollowUpResponse", "Service/SDoHFollowUpBS",
                      "Process/SDoHFollowUpBP", "Operation/SDoHFollowUpBO"]
    for rel in legacy_classes:
        text = body(CARECONNECT_SRC / "CareConnect" / f"{rel}.cls")
        assert "%AI" not in text, f"CareConnect/{rel}.cls needs AI Hub"


def test_companion_tools_are_declared_by_the_toolset():
    declared = set(re.findall(r'<Tool Name="(\w+)"', body(TOOLSET)))
    companion = {n for n, t in _sidecar_tools().items() if t["backend"] == "companion"}
    assert companion <= declared

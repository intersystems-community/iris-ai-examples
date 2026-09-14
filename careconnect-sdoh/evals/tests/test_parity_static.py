"""Static parity: the Python mirror vs the ObjectScript it claims to mirror.

`test_parity.py` is the stronger check — it calls the real classmethods and
compares bytes — but it needs a running IRIS, so it skips in CI, on a laptop
without Docker, and in exactly the situation where drift creeps in. It did skip,
and the mirror drifted for months: the ObjectScript grew a sixth domain
(Transportation Access) with its own keywords and moved both priority
thresholds, and nothing failed.

This suite reads `SDoHToolSet.cls` off disk and compares it to the mirror's rule
table. No IRIS, no Docker, no network. It cannot prove the two produce identical
bytes — that is `test_parity.py`'s job — but it does prove they encode the same
rule, which is the part that silently rots.

The mirror is the thing under test. The ObjectScript is the source of truth: when
these disagree, change the Python.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careconnect_evals import scorers, tools_local  # noqa: E402
from careconnect_evals.tools_local import (  # noqa: E402
    DOMAIN_ORDER,
    DOMAIN_RULES,
    PRIORITY_THRESHOLDS,
)

CLS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "CareConnect"
    / "Tools"
    / "SDoHToolSet.cls"
)

# Methods whose output the mirror reproduces verbatim. The interop tools are
# simulated rather than mirrored, so their literals are deliberately excluded.
DETERMINISTIC_METHODS = (
    "SearchPatients",
    "FetchPatientSummary",
    "SearchSDoHProtocols",
    "AssessSDoHRisk",
    "DraftCarePlan",
)


# ── reading the ObjectScript ────────────────────────────────────────────────


def _string_literals(code: str) -> list:
    """Every ObjectScript string literal in `code`, in order.

    A regex cannot do this: ObjectScript builds output by concatenating
    `_"literal"_`, so `"([^"]*)"` happily matches the *code* between two
    literals. It also escapes a quote by doubling it, which a regex reads as an
    empty string followed by garbage. So: scan, and treat `""` inside a literal
    as one character."""
    out, i, n = [], 0, len(code)
    while i < n:
        if code[i] != '"':
            i += 1
            continue
        i += 1
        buf = []
        while i < n:
            if code[i] == '"':
                if i + 1 < n and code[i + 1] == '"':  # escaped quote
                    buf.append('"')
                    i += 2
                    continue
                i += 1
                break
            buf.append(code[i])
            i += 1
        out.append("".join(buf))
    return out


def _method_body(source: str, name: str) -> str:
    """The body of one ClassMethod, from its signature to the closing brace in
    column 1. Brace-counting is unnecessary — this file indents every nested
    block, so the first line that is exactly '}' ends the method."""
    start = re.search(rf"^ClassMethod {name}\(", source, re.M)
    assert start, f"{name} not found in {CLS_PATH.name}"
    rest = source[start.end() :]
    end = re.search(r"^\}$", rest, re.M)
    assert end, f"no closing brace found for {name}"
    return rest[: end.start()]


@pytest.fixture(scope="module")
def cls_source() -> str:
    assert CLS_PATH.exists(), (
        f"canonical ObjectScript not found at {CLS_PATH} — the mirror's docstring "
        "points here, so either the path moved or the source of truth is missing"
    )
    return CLS_PATH.read_text()


@pytest.fixture(scope="module")
def assess(cls_source: str) -> str:
    return _method_body(cls_source, "AssessSDoHRisk")


@pytest.fixture(scope="module")
def objectscript_rule(assess: str) -> dict:
    """Reconstruct the rule from the ObjectScript: printed label -> keywords and
    the two values the $Select can return."""
    # Set econ = $Select((summaryLC["unemploy")||(summaryLC["job"):"HIGH", 1:"LOW")
    selects = {}
    for var, tests, hit, miss in re.findall(
        r'Set (\w+) = \$Select\((.*?):"(\w+)", 1:"(\w+)"\)', assess
    ):
        selects[var] = {
            "keywords": tuple(re.findall(r'summaryLC\["([^"]+)"', tests)),
            "hit": hit,
            "miss": miss,
        }

    #     Set out = out_"  Economic Stability:      "_econ_$Char(10)
    printed = re.findall(r'Set out = out_"(\s+[\w/ ]+:\s+)"_(\w+)_\$Char\(10\)', assess)

    rule, prefixes = {}, {}
    for literal, var in printed:
        label = literal.strip().rstrip(":")
        assert var in selects, f"the ObjectScript prints {var} but never computes it"
        rule[label] = selects[var]
        prefixes[label] = literal
    return {"rule": rule, "prefixes": prefixes, "vars": selects}


# ── the rule itself ─────────────────────────────────────────────────────────


def test_the_mirror_scores_the_same_domains_in_the_same_order(objectscript_rule):
    """Order is load-bearing: `scorers.parse_assessment` reads the printed block,
    and a reordered mirror would still parse while no longer matching bytes."""
    assert DOMAIN_ORDER == list(objectscript_rule["rule"]), (
        "domain list or order has drifted from the ObjectScript"
    )


def test_every_domain_scored_by_the_objectscript_is_also_summed_by_it(assess):
    """Guards the ObjectScript against itself: a domain that is printed but left
    out of the For loop would not count toward the priority, and the mirror would
    faithfully copy the bug only if it read the loop rather than the print block."""
    loop = re.search(r"For d = ([\w, ]+) \{", assess)
    assert loop, "the highCount For loop is gone — reread AssessSDoHRisk"
    summed = [v.strip() for v in loop.group(1).split(",")]
    printed = re.findall(r'Set out = out_"\s+[\w/ ]+:\s+"_(\w+)_\$Char\(10\)', assess)
    assert summed == printed, "a scored domain is printed but not counted, or vice versa"


@pytest.mark.parametrize("label", list(DOMAIN_RULES))
def test_domain_keywords_match_the_objectscript(objectscript_rule, label):
    truth = objectscript_rule["rule"].get(label)
    assert truth is not None, f"the ObjectScript no longer scores {label!r}"
    assert DOMAIN_RULES[label]["keywords"] == truth["keywords"]


@pytest.mark.parametrize("label", list(DOMAIN_RULES))
def test_domain_values_match_the_objectscript(objectscript_rule, label):
    """Health Care Access is the one domain whose miss value is MEDIUM, not LOW.
    A mirror that flattened that to LOW would change every precision figure in
    the report without changing a single domain count."""
    truth = objectscript_rule["rule"][label]
    assert DOMAIN_RULES[label]["hit"] == truth["hit"]
    assert DOMAIN_RULES[label]["miss"] == truth["miss"]


def test_the_scorer_parses_every_domain_the_rule_scores(objectscript_rule):
    """`scorers.parse_assessment` reads the printed block with one regex per
    domain, so a domain missing from `_DOMAIN_LABELS` is silently unscored: L1
    passes because it never compares that domain, and L1b's precision improves
    because a real elevated need is never counted as missed. That is how the sixth
    domain stayed invisible for months."""
    assert list(scorers._DOMAIN_LABELS.values()) == list(objectscript_rule["rule"]), (
        "scorers._DOMAIN_LABELS has drifted from the domains AssessSDoHRisk prints"
    )


def test_the_plan_domains_are_domains(objectscript_rule):
    """PLAN_DOMAINS is a subset of the scored domains — a typo there silently
    shrinks the L5 profile key rather than failing."""
    unknown = set(scorers.PLAN_DOMAINS) - set(scorers._DOMAIN_LABELS)
    assert not unknown, f"PLAN_DOMAINS names domains the scorer cannot parse: {sorted(unknown)}"


def test_priority_thresholds_match_the_objectscript(assess):
    m = re.search(
        r'Set priority = \$Select\(highCount >= (\d+):"URGENT", '
        r'highCount >= (\d+):"HIGH", 1:"ROUTINE"\)',
        assess,
    )
    assert m, "priority $Select has changed shape — reread AssessSDoHRisk"
    assert PRIORITY_THRESHOLDS == (("URGENT", int(m.group(1))), ("HIGH", int(m.group(2))))


def test_the_denominator_is_the_number_of_domains_actually_scored(assess):
    m = re.search(r"/(\d+) domains elevated", assess)
    assert m, "the '(n/N domains elevated)' tail has changed shape"
    assert int(m.group(1)) == len(DOMAIN_RULES) == len(DOMAIN_ORDER)


# ── the printed shape ───────────────────────────────────────────────────────


@pytest.mark.parametrize("label", list(DOMAIN_RULES))
def test_the_label_column_formula_reproduces_the_objectscript_literal(objectscript_rule, label):
    """The mirror builds these lines from one padding rule rather than six hand
    literals. If that formula is right for all six, it stays right when a
    seventh domain arrives."""
    assert tools_local.assessment_line(label, "X").rstrip("X") == objectscript_rule["prefixes"][label]


# Literals the mirror is entitled not to reproduce, each for a stated reason.
# Anything else the ObjectScript can print, the mirror must be able to print too.
EXEMPT_LITERALS = {
    # The mirror's PATIENTS dict is a constant and is never empty, so the
    # empty-database branch has no counterpart. `test_parity.py` covers the live
    # table; nothing can cover a state the mirror cannot enter.
    "No patients in database. Run CareConnect.Setup.DemoData.Load() to seed demo patients.",
}


@pytest.fixture(scope="module")
def mirror_corpus() -> str:
    """Everything the mirror can say, plus its source.

    Comparing against the source alone is too weak in one direction and too
    strong in the other: the mirror builds `"  Economic Stability:      "` from a
    padding formula (so the literal is absent from the source but present in the
    output), and black wraps long messages across lines (so a literal the mirror
    definitely emits is not a contiguous substring of the file). Exercising the
    tools and keeping the source for keyword constants covers both."""
    c = tools_local.LocalToolClient()
    out = [Path(tools_local.__file__).read_text()]

    out.append(c.SearchPatients())
    out.append(c.SearchPatients("no-such-patient"))
    out.append(c.FetchPatientSummary(""))
    out.append(c.FetchPatientSummary("no-such-patient"))
    out.append(c.SearchSDoHProtocols(""))
    out.append(c.SearchSDoHProtocols("nothing matches this"))
    # Every protocol branch, including the ones no demo patient reaches.
    out.append(
        c.SearchSDoHProtocols(
            "diabetes hypertension blood pressure heart chf bnp depression phq "
            "mental food nutrition anemia housing transport financial uninsured"
        )
    )
    out.append(c.AssessSDoHRisk("", ""))
    out.append(c.DraftCarePlan("", ""))
    for pid in tools_local.PATIENTS:
        summary = c.FetchPatientSummary(pid)
        scores = c.AssessSDoHRisk(pid, summary)
        out += [
            c.SearchPatients(tools_local.PATIENTS[pid]["Name"]),
            summary,
            c.SearchSDoHProtocols(tools_local.PATIENTS[pid]["Conditions"]),
            scores,
            c.DraftCarePlan(pid, scores),
        ]
    return "\n".join(out)


def test_every_output_literal_in_the_objectscript_appears_in_the_mirror(cls_source, mirror_corpus):
    """Catches punctuation drift, which byte-parity tests catch and human review
    does not. The mirror had em dashes where the ObjectScript has hyphens in
    every DraftCarePlan step — invisible on screen, four failures in
    test_parity.py."""
    missing = []
    for method in DETERMINISTIC_METHODS:
        for literal in _string_literals(_method_body(cls_source, method)):
            # Short literals are punctuation and separators, not output text.
            if len(literal.strip()) < 8:
                continue
            # SQL is the mirror's one structural divergence: it reads a dict, not
            # a table, so no SELECT from the ObjectScript can appear in it.
            if re.match(r"\s*(SELECT|INSERT|UPDATE|DELETE|CALL)\b", literal, re.I):
                continue
            if literal in EXEMPT_LITERALS:
                continue
            if literal not in mirror_corpus:
                missing.append((method, literal))
    assert not missing, "output literals present in the ObjectScript but not the mirror:\n" + "\n".join(
        f"  {m}: {lit!r}" for m, lit in missing
    )

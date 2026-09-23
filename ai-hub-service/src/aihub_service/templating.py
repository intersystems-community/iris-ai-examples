"""The one small expression language the config files use.

Two jobs, both deliberately tiny so a config reviewer can read every rule:

* ``render("${args.patientId}", scope)`` — substitute values into tool bindings
  and playbook arguments. ``${a.b|lower}``, ``${a.b|default:routine}``.
* ``truthy("context.followUp and not result.Assess contains 'URGENT'", scope)``
  — decide whether a playbook step or a SQL case applies.

No attribute access, no calls, no arithmetic: a config file that could run code
would be a second programming model, which is the thing a service is meant to
spare its callers.
"""

from __future__ import annotations

import re
from typing import Any

_REF = re.compile(r"\$\{(?P<expr>[^}]+)\}")
_CLAUSE = re.compile(
    r"^\s*(?P<neg>not\s+)?(?P<path>[A-Za-z_][\w.]*)"
    r"(?:\s+(?P<op>contains|==|!=)\s+(?P<q>['\"])(?P<lit>.*?)(?P=q))?\s*$"
)


def lookup(path: str, scope: dict) -> Any:
    cur: Any = scope
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _apply(expr: str, scope: dict) -> Any:
    path, *filters = [p.strip() for p in expr.split("|")]
    value = lookup(path, scope)
    for f in filters:
        name, _, arg = f.partition(":")
        if name == "default":
            if value is None or value == "":
                value = arg
        elif name == "lower":
            value = "" if value is None else str(value).lower()
        elif name == "upper":
            value = "" if value is None else str(value).upper()
        else:
            raise ValueError(f"unknown filter '{name}' in ${{{expr}}}")
    return value


def render(template: Any, scope: dict) -> Any:
    """Render one template. A string that is exactly one reference keeps the
    value's type, so ``${context.followUp}`` stays a bool."""
    if isinstance(template, dict):
        return {k: render(v, scope) for k, v in template.items()}
    if isinstance(template, list):
        return [render(v, scope) for v in template]
    if not isinstance(template, str):
        return template
    whole = _REF.fullmatch(template)
    if whole:
        return _apply(whole.group("expr"), scope)

    def sub(m: re.Match) -> str:
        v = _apply(m.group("expr"), scope)
        return "" if v is None else str(v)

    return _REF.sub(sub, template)


def truthy(expr: str | bool | None, scope: dict) -> bool:
    """Evaluate ``a and b or c`` (``and`` binds tighter); each clause is
    ``[not] path [contains|==|!= 'literal']``. Literals may not contain " and "
    or " or " — this is a config language, not a parser exercise."""
    if expr is None:
        return True
    if isinstance(expr, bool):
        return expr
    return any(
        all(_clause(c, scope) for c in re.split(r"\s+and\s+", alt))
        for alt in re.split(r"\s+or\s+", expr.strip())
    )


def _clause(clause: str, scope: dict) -> bool:
    m = _CLAUSE.match(clause)
    if not m:
        raise ValueError(f"cannot parse condition clause: {clause!r}")
    value = lookup(m.group("path"), scope)
    op, lit = m.group("op"), m.group("lit")
    if op is None:
        ok = _is_true(value)
    elif op == "contains":
        ok = lit in ("" if value is None else str(value))
    elif op == "==":
        ok = str(value) == lit
    else:
        ok = str(value) != lit
    return not ok if m.group("neg") else ok


def _is_true(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)

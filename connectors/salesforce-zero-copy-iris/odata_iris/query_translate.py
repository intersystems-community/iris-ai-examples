"""Translates OData v4 query options ($filter, $select, $top, $skip,
$orderby) into a parameterized IRIS SQL SELECT statement.

Injection defense, precisely stated:
  - Column/property names are NEVER taken from client input and placed
    into SQL text unless they exactly match a name already declared in
    the target EntitySet's whitelist (schema.EntitySet.column_names).
    Anything else raises ODataQueryError before touching SQL.
  - Literal values (comparison right-hand sides) are NEVER interpolated
    into SQL text. They are collected into a `params` list and referenced
    in the SQL text only as '?' placeholders, to be bound by the DB-API
    driver's parameterized-execute — exactly the mechanism that makes
    SQL injection structurally impossible for those values.
  - $top / $skip are validated as plain non-negative integers via a
    strict regex + int(); a value that is not purely digits (e.g. an
    injection attempt like "1;DROP TABLE x") raises ODataQueryError and
    is never placed in SQL at all, parameterized or otherwise, because
    IRIS's TOP/SKIP-equivalent SQL syntax does not accept a bind
    parameter in that position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import EntitySet

MAX_TOP = 5000
DEFAULT_TOP = 100

_INT_RE = re.compile(r"^\d+$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ODataQueryError(ValueError):
    """Raised for any malformed or disallowed OData query option.
    Deliberately a plain ValueError subclass with no SQL fragments in
    its message beyond the offending client-supplied token, so callers
    can render it as an HTTP 400 without leaking query shape."""


@dataclass(frozen=True)
class Query:
    sql: str
    params: list[object]
    skip: int = 0


# ---------------------------------------------------------------------------
# $select
# ---------------------------------------------------------------------------


def translate_select(entity_set: EntitySet, select_raw: str | None) -> list[str]:
    if not select_raw:
        return [c.name for c in entity_set.columns]
    names = [p.strip() for p in select_raw.split(",") if p.strip()]
    for n in names:
        _require_known_column(entity_set, n)
    return names


# ---------------------------------------------------------------------------
# $top / $skip
# ---------------------------------------------------------------------------


def translate_top(top_raw: str | None) -> int:
    if top_raw is None:
        return DEFAULT_TOP
    if not _INT_RE.match(top_raw):
        raise ODataQueryError(f"$top must be a non-negative integer, got {top_raw!r}")
    value = int(top_raw)
    if value > MAX_TOP:
        raise ODataQueryError(f"$top exceeds maximum of {MAX_TOP}")
    return value


def translate_skip(skip_raw: str | None) -> int:
    if skip_raw is None:
        return 0
    if not _INT_RE.match(skip_raw):
        raise ODataQueryError(f"$skip must be a non-negative integer, got {skip_raw!r}")
    return int(skip_raw)


# ---------------------------------------------------------------------------
# $orderby
# ---------------------------------------------------------------------------


def translate_orderby(entity_set: EntitySet, orderby_raw: str | None) -> str | None:
    if not orderby_raw:
        return None
    clauses = []
    for part in orderby_raw.split(","):
        part = part.strip()
        tokens = part.split()
        if len(tokens) == 1:
            prop, direction = tokens[0], "asc"
        elif len(tokens) == 2:
            prop, direction = tokens[0], tokens[1].lower()
        else:
            raise ODataQueryError(f"malformed $orderby clause {part!r}")
        if direction not in ("asc", "desc"):
            raise ODataQueryError(f"$orderby direction must be asc or desc, got {direction!r}")
        _require_known_column(entity_set, prop)
        clauses.append(f"{prop} {direction.upper()}")
    return ", ".join(clauses)


# ---------------------------------------------------------------------------
# $filter — tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
      \s*(
        (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<comma>,)
      | (?P<string>'(?:[^']|'')*')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      )\s*
    """,
    re.VERBOSE,
)

_COMPARISON_OPS = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
_FUNCTIONS = {
    "contains": "%{}%",
    "startswith": "{}%",
    "endswith": "%{}",
}


def _tokenize(filter_raw: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(filter_raw):
        m = _TOKEN_RE.match(filter_raw, pos)
        if not m or m.end() == pos:
            raise ODataQueryError(f"could not parse $filter near position {pos}")
        for kind in ("lparen", "rparen", "comma", "string", "number", "ident"):
            val = m.group(kind)
            if val is not None:
                tokens.append(val)
                break
        pos = m.end()
    return tokens


class _Parser:
    """Small recursive-descent parser for the supported $filter subset:
    comparisons (eq/ne/gt/ge/lt/le), and/or/not, parens, and the
    contains/startswith/endswith string functions. Produces SQL text
    plus a params list directly (no separate AST) since the grammar is
    small enough that this stays readable.
    """

    def __init__(self, tokens: list[str], entity_set: EntitySet):
        self.tokens = tokens
        self.pos = 0
        self.entity_set = entity_set
        self.params: list[object] = []

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> str:
        tok = self._peek()
        if tok is None:
            raise ODataQueryError("unexpected end of $filter expression")
        self.pos += 1
        return tok

    def _expect(self, literal: str) -> None:
        tok = self._advance()
        if tok.lower() != literal:
            raise ODataQueryError(f"expected {literal!r}, got {tok!r}")

    def parse(self) -> str:
        sql = self._or_expr()
        if self.pos != len(self.tokens):
            raise ODataQueryError(f"unexpected trailing token {self._peek()!r} in $filter")
        return sql

    def _or_expr(self) -> str:
        left = self._and_expr()
        while self._peek() is not None and self._peek().lower() == "or":
            self._advance()
            right = self._and_expr()
            left = f"({left} OR {right})"
        return left

    def _and_expr(self) -> str:
        left = self._not_expr()
        while self._peek() is not None and self._peek().lower() == "and":
            self._advance()
            right = self._not_expr()
            left = f"({left} AND {right})"
        return left

    def _not_expr(self) -> str:
        if self._peek() is not None and self._peek().lower() == "not":
            self._advance()
            inner = self._primary()
            return f"(NOT {inner})"
        return self._primary()

    def _primary(self) -> str:
        tok = self._peek()
        if tok == "(":
            self._advance()
            inner = self._or_expr()
            if self._peek() != ")":
                raise ODataQueryError("missing closing parenthesis in $filter")
            self._advance()
            return f"({inner})"

        if tok is not None and tok.lower() in _FUNCTIONS:
            return self._function_call()

        return self._comparison()

    def _function_call(self) -> str:
        func = self._advance().lower()
        if self._peek() != "(":
            raise ODataQueryError(f"expected '(' after {func}")
        self._advance()
        prop = self._advance()
        _require_known_column(self.entity_set, prop)
        if self._peek() != ",":
            raise ODataQueryError(f"expected ',' in {func}(...)")
        self._advance()
        literal_tok = self._advance()
        value = _parse_string_literal(literal_tok)
        if self._peek() != ")":
            raise ODataQueryError(f"missing closing parenthesis in {func}(...)")
        self._advance()
        pattern = _FUNCTIONS[func].format(value)
        self.params.append(pattern)
        return f"{prop} LIKE ?"

    def _comparison(self) -> str:
        prop = self._advance()
        _require_known_column(self.entity_set, prop)
        op_tok = self._peek()
        if op_tok is None or op_tok.lower() not in _COMPARISON_OPS:
            raise ODataQueryError(
                f"expected comparison operator after {prop!r}, got {op_tok!r}"
            )
        op = _COMPARISON_OPS[self._advance().lower()]
        literal_tok = self._advance()
        value = self._literal_value(literal_tok, op)
        if value is _NULL:
            if op == "=":
                return f"{prop} IS NULL"
            if op == "<>":
                return f"{prop} IS NOT NULL"
            raise ODataQueryError("null only supports eq/ne")
        self.params.append(value)
        return f"{prop} {op} ?"

    def _literal_value(self, tok: str, op: str):
        if tok.lower() == "null":
            return _NULL
        if tok.lower() in ("true", "false"):
            return 1 if tok.lower() == "true" else 0
        if tok.startswith("'"):
            return _parse_string_literal(tok)
        try:
            return int(tok) if "." not in tok else float(tok)
        except ValueError:
            raise ODataQueryError(f"malformed literal {tok!r} in $filter")


class _Null:
    pass


_NULL = _Null()


def _parse_string_literal(tok: str) -> str:
    if not (tok.startswith("'") and tok.endswith("'") and len(tok) >= 2):
        raise ODataQueryError(f"expected string literal, got {tok!r}")
    # OData escapes an embedded quote as '' — undo that.
    return tok[1:-1].replace("''", "'")


def translate_filter(entity_set: EntitySet, filter_raw: str | None) -> tuple[str | None, list[object]]:
    if not filter_raw:
        return None, []
    tokens = _tokenize(filter_raw)
    parser = _Parser(tokens, entity_set)
    sql = parser.parse()
    return sql, parser.params


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _require_known_column(entity_set: EntitySet, name: str) -> None:
    if not _IDENT_RE.match(name) or name not in entity_set.column_names:
        raise ODataQueryError(
            f"unknown property {name!r} for entity set {entity_set.name!r}"
        )


# ---------------------------------------------------------------------------
# top-level entry point
# ---------------------------------------------------------------------------


def build_query(
    entity_set: EntitySet,
    *,
    select: str | None = None,
    filter: str | None = None,
    top: str | None = None,
    skip: str | None = None,
    orderby: str | None = None,
) -> Query:
    """Builds one parameterized SELECT statement for `entity_set`,
    honoring the given (still string-typed, exactly as they arrive on
    the query string) OData options. Raises ODataQueryError for any
    option this module can't safely translate.
    """

    columns = translate_select(entity_set, select)
    where_sql, params = translate_filter(entity_set, filter)
    order_sql = translate_orderby(entity_set, orderby)
    top_n = translate_top(top)
    skip_n = translate_skip(skip)

    column_list = ", ".join(columns)
    sql = f"SELECT TOP {top_n + skip_n} {column_list} FROM {entity_set.table}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    if order_sql:
        sql += f" ORDER BY {order_sql}"

    # IRIS SQL has no OFFSET-before-9.x-style clause guaranteed across all
    # deployment targets in this repo's registry; skip is applied by the
    # caller in Python over the TOP-bounded result set (see service.py),
    # which is correct and simple for the row counts a Data Cloud
    # federation query realistically pages through. skip_n is threaded
    # through Query for the caller to slice with, not embedded in SQL.
    return Query(sql=sql, params=params, skip=skip_n)

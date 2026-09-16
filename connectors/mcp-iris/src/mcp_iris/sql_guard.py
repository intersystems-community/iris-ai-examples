"""Read-only SQL enforcement for the IRIS MCP server.

This module is the actual security boundary described in the task brief: a
"naive keyword check" (``if "insert" in sql.lower(): reject``) is not good
enough, because it is trivially defeated by comment-splitting, string
literals containing the keyword as data, multi-statement stacking, or
data-modifying CTEs. ``assert_read_only`` instead:

1. Rejects any comment that sits directly against a word character with no
   surrounding whitespace (the classic ``IN/**/SERT`` keyword-splitting
   trick), *before* anything else runs.
2. Splits the input into statements using a real SQL tokenizer
   (``sqlparse``), which understands quoting and comments, and rejects
   anything that is not exactly one non-empty statement (closes semicolon
   stacking and comment-hidden trailing statements).
3. Strips comments and masks string/quoted-identifier literals, so keyword
   matching can't be fooled by literal data ('DROP TABLE') and can't be
   evaded by hiding a keyword inside a comment either.
4. Requires the statement to *start* with ``SELECT`` or ``WITH``.
5. Scans the whole statement (not just the first token) for any
   data-modifying keyword, so a data-modifying CTE body
   (``WITH x AS (INSERT ... ) SELECT * FROM x``) is caught even though the
   statement technically starts with ``WITH``.

None of this is a general-purpose SQL parser or a substitute for running the
query against IRIS as a role that literally lacks write privileges (belt AND
suspenders is the right posture for a tool an LLM agent calls autonomously).
"""

from __future__ import annotations

import re

import sqlparse

__all__ = ["SQLGuardError", "assert_read_only"]


class SQLGuardError(ValueError):
    """Raised when a SQL statement fails the read-only safety check."""


# Keywords that, if they appear anywhere in the statement, indicate it is not
# a pure read-only SELECT. Deliberately broader than the six the task names
# explicitly (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE) plus CALL/GRANT: it
# also blocks REVOKE, CREATE, EXEC/EXECUTE, MERGE, INTO (blocks
# `SELECT ... INTO new_table`), SET, LOCK, and a handful of other
# vendor-specific data/privilege/session-mutating statements.
_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CALL",
    "GRANT",
    "REVOKE",
    "CREATE",
    "EXEC",
    "EXECUTE",
    "MERGE",
    "INTO",
    "LOCK",
    "SET",
    "PRAGMA",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "REPLACE",
    "RENAME",
    "COPY",
    "BACKUP",
    "RESTORE",
    "KILL",
    "SHUTDOWN",
    "UNLOCK",
)

_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)

# A comment delimiter with no whitespace between it and a word character on
# the adjacent side is treated as an attempt to split a keyword in two
# (`IN/**/SERT`) or to smuggle content immediately next to real SQL
# (`DROP/*x*/TABLE`). Legitimate formatting never needs this.
_SUSPICIOUS_COMMENT_ADJACENCY_RE = re.compile(r"(\w)(--|/\*)|(\*/)(\w)")

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# SQL single-quoted string literal, with '' as the escaped-quote sequence.
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
# Double-quoted delimited identifier (ANSI SQL / IRIS).
_DELIMITED_IDENTIFIER_RE = re.compile(r'"(?:[^"]|"")*"')

_LEADING_KEYWORD_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def _strip_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT_RE.sub("", sql)
    sql = _LINE_COMMENT_RE.sub("", sql)
    return sql


def _mask_literals(sql: str) -> str:
    sql = _STRING_LITERAL_RE.sub("'X'", sql)
    sql = _DELIMITED_IDENTIFIER_RE.sub('"X"', sql)
    return sql


def _split_statements(sql: str) -> list[str]:
    """Split into statements using a real SQL tokenizer.

    sqlparse.split() is quote- and comment-aware, unlike a naive
    ``sql.split(";")``, so a semicolon inside a string literal or a comment
    does not falsely count as a statement boundary.
    """
    try:
        statements = sqlparse.split(sql)
    except Exception as exc:  # pragma: no cover - sqlparse is very lenient
        raise SQLGuardError(f"could not parse SQL: {exc}") from exc
    return [s for s in statements if s.strip()]


def assert_read_only(sql: str) -> None:
    """Raise ``SQLGuardError`` unless ``sql`` is a single read-only query.

    On success, returns ``None`` — the query is safe to hand to the driver.
    """
    if not isinstance(sql, str):
        raise SQLGuardError("query must be a string")

    if not sql.strip():
        raise SQLGuardError("query is empty")

    # Layer 1: reject keyword-splitting via comments before anything else,
    # so a later "helpful" comment-stripping pass can't be tricked into
    # reforming a forbidden keyword from two otherwise-innocuous pieces.
    if _SUSPICIOUS_COMMENT_ADJACENCY_RE.search(sql):
        raise SQLGuardError(
            "comment sits directly against a token with no whitespace; "
            "this is a known keyword-splitting bypass pattern and is "
            "rejected outright"
        )

    # Layer 2: exactly one statement, using a real tokenizer so quoted
    # semicolons/comments don't confuse the boundary detection.
    statements = _split_statements(sql)
    if len(statements) == 0:
        raise SQLGuardError("query contains no statement (comment-only?)")
    if len(statements) > 1:
        raise SQLGuardError(
            f"multi-statement queries are not allowed ({len(statements)} "
            "statements detected)"
        )

    statement = statements[0]

    # Layer 3: strip comments, then mask string/identifier literals so
    # keyword matching can't be fooled by data, and can't be dodged by
    # putting a keyword only inside a comment either (it's gone by now).
    no_comments = _strip_comments(statement)
    if not no_comments.strip():
        raise SQLGuardError("query contains no statement (comment-only?)")

    masked = _mask_literals(no_comments)

    # A leftover semicolon after masking means sqlparse's splitter missed a
    # boundary (defense in depth; not expected to trigger in practice).
    body = masked.strip()
    if body.endswith(";"):
        body = body[:-1]
    if ";" in body:
        raise SQLGuardError("multi-statement queries are not allowed")

    # Layer 4: must start with SELECT or WITH.
    if not _LEADING_KEYWORD_RE.match(masked):
        raise SQLGuardError(
            "only SELECT and WITH (CTE) statements are allowed for "
            "read-only queries"
        )

    # Layer 5: no data/privilege/session-mutating keyword anywhere in the
    # statement — this is what catches a WITH ... AS (INSERT ...) writable
    # CTE even though the statement starts with the allowed WITH keyword.
    match = _FORBIDDEN_RE.search(masked)
    if match:
        raise SQLGuardError(
            f"statement contains forbidden keyword: {match.group(1).upper()}"
        )

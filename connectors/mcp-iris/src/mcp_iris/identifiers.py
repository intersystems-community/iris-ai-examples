"""Strict identifier validation.

Table/column/schema names that get interpolated into SQL text (because
DB-API parameter placeholders cannot stand in for identifiers) must be
validated against an allow-list pattern rather than merely escaped, or a
"table name" parameter becomes a second, unguarded SQL injection surface
right next to the one ``sql_guard`` closes for the free-text query tool.
"""

from __future__ import annotations

import re

__all__ = ["InvalidIdentifierError", "validate_identifier", "validate_qualified_name"]


class InvalidIdentifierError(ValueError):
    pass


# A conservative superset of IRIS unquoted identifiers: letters, digits,
# and underscore, not starting with a digit. Real IRIS class/table names
# also allow embedded "." in the class-name sense, which is handled by
# validate_qualified_name splitting on "." first.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_MAX_IDENT_LEN = 128


def validate_identifier(name: str) -> str:
    """Validate a single unqualified SQL identifier (table, column, ...).

    Raises ``InvalidIdentifierError`` for anything that isn't a plain
    word-like token, including empty strings, whitespace, quotes,
    semicolons, SQL keywords used as an injection vector, or names that
    are suspiciously long.
    """
    if not isinstance(name, str) or not name:
        raise InvalidIdentifierError(f"identifier must be a non-empty string, got {name!r}")
    if len(name) > _MAX_IDENT_LEN:
        raise InvalidIdentifierError(f"identifier too long: {name!r}")
    if not _IDENT_RE.match(name):
        raise InvalidIdentifierError(f"invalid identifier: {name!r}")
    return name


def validate_qualified_name(name: str) -> str:
    """Validate a ``schema.table`` or bare ``table`` identifier."""
    if not isinstance(name, str) or not name:
        raise InvalidIdentifierError(f"identifier must be a non-empty string, got {name!r}")
    parts = name.split(".")
    if len(parts) not in (1, 2):
        raise InvalidIdentifierError(f"invalid qualified identifier: {name!r}")
    for part in parts:
        validate_identifier(part)
    return name

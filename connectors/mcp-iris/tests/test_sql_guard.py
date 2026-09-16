"""Tests for the read-only SQL guard.

Written before sql_guard.py's final behavior was locked in, per CLAUDE.md's
test-first policy. These cases are the actual security boundary for the
`run_query` MCP tool: every one of them is either a legitimate read-only query
that must be allowed, or an adversarial payload that must be rejected.
"""

from __future__ import annotations

import pytest

from mcp_iris.sql_guard import SQLGuardError, assert_read_only


# ---------------------------------------------------------------------------
# Queries that MUST be allowed
# ---------------------------------------------------------------------------

ALLOWED_QUERIES = [
    "SELECT * FROM Sample.Person",
    "select id, name from Sample.Person where age > 21",
    "SELECT TOP 10 * FROM Sample.Person ORDER BY Name",
    "SELECT * FROM Sample.Person -- trailing line comment is fine",
    "SELECT * FROM Sample.Person /* trailing block comment is fine */",
    "  \n  SELECT * FROM Sample.Person  \n  ",
    "SELECT * FROM Sample.Person;",  # single trailing semicolon is fine
    "SELECT * FROM Sample.Person;   \n  ",
    "WITH recent AS (SELECT * FROM Sample.Person WHERE Age > 21) "
    "SELECT * FROM recent",
    "SELECT COUNT(*) FROM Sample.Person",
    "SELECT * FROM Sample.Person WHERE Name = 'DROP TABLE not really'",
    "SELECT * FROM Sample.Person WHERE Notes LIKE '%update this record%'",
    "SELECT * FROM Sample.Person WHERE Name = 'O''Brien; DELETE FROM x'",
    "SELECT VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS sim "
    "FROM KG.Ticket ORDER BY sim DESC",
]


@pytest.mark.parametrize("sql", ALLOWED_QUERIES)
def test_allowed_queries_pass(sql: str) -> None:
    # Must not raise.
    assert_read_only(sql)


# ---------------------------------------------------------------------------
# Queries that MUST be rejected: obvious cases
# ---------------------------------------------------------------------------

OBVIOUSLY_REJECTED = [
    "INSERT INTO Sample.Person (Name) VALUES ('x')",
    "UPDATE Sample.Person SET Name = 'x'",
    "DELETE FROM Sample.Person",
    "DROP TABLE Sample.Person",
    "ALTER TABLE Sample.Person ADD COLUMN x INT",
    "TRUNCATE TABLE Sample.Person",
    "CALL Sample.SomeProcedure()",
    "GRANT SELECT ON Sample.Person TO Bob",
    "REVOKE SELECT ON Sample.Person FROM Bob",
    "CREATE TABLE Evil (id INT)",
    "MERGE INTO Sample.Person USING Staging ON (1=1) "
    "WHEN MATCHED THEN UPDATE SET Name = 'x'",
    "EXEC Sample.SomeProcedure",
    "EXECUTE Sample.SomeProcedure",
]


@pytest.mark.parametrize("sql", OBVIOUSLY_REJECTED)
def test_obviously_dangerous_queries_rejected(sql: str) -> None:
    with pytest.raises(SQLGuardError):
        assert_read_only(sql)


# ---------------------------------------------------------------------------
# Queries that MUST be rejected: bypass attempts
# ---------------------------------------------------------------------------

BYPASS_ATTEMPTS = [
    # Multi-statement stacking via semicolon.
    "SELECT * FROM Sample.Person; DROP TABLE Sample.Person",
    "SELECT * FROM Sample.Person;DROP TABLE Sample.Person;",
    "SELECT 1; DELETE FROM Sample.Person;",
    # Comment-hidden statement smuggling.
    "SELECT * FROM Sample.Person; -- \nDROP TABLE Sample.Person",
    "SELECT * FROM Sample.Person /* */; DROP TABLE Sample.Person",
    # Keyword split via inline block comment (comment stripping must not
    # leave the pieces re-joined into a still-valid keyword by accident,
    # and must not be foolable into ignoring the keyword either).
    "IN/**/SERT INTO Sample.Person (Name) VALUES ('x')",
    "SELECT * FROM Sample.Person WHERE 1=1; /*comment*/DROP/*comment*/ TABLE Sample.Person",
    # Case tricks.
    "InSeRt INTO Sample.Person (Name) VALUES ('x')",
    "dRoP TABLE Sample.Person",
    "SeLeCt * FROM Sample.Person; deLeTe FROM Sample.Person",
    # Whitespace/newline/tab tricks.
    "DROP\tTABLE\nSample.Person",
    "   DROP   TABLE   Sample.Person",
    # Nested statement inside parens / subquery that writes.
    "SELECT * FROM (DELETE FROM Sample.Person) AS x",
    # Writable CTE (a WITH-prefixed statement whose body still mutates data).
    "WITH x AS (INSERT INTO Sample.Person (Name) VALUES ('x') RETURNING Id) "
    "SELECT * FROM x",
    "WITH x AS (SELECT 1) UPDATE Sample.Person SET Name = 'x'",
    # SELECT ... INTO used to materialize a table (not a read-only op).
    "SELECT * INTO NewTable FROM Sample.Person",
    # Leading noise trying to dodge a naive "starts with SELECT" check.
    "; DROP TABLE Sample.Person; SELECT 1",
    "(SELECT 1); DROP TABLE Sample.Person",
    # Not a SELECT/WITH at all.
    "SET OPTION SomeOption = 1",
    "PRAGMA table_info(Sample.Person)",
]


@pytest.mark.parametrize("sql", BYPASS_ATTEMPTS)
def test_bypass_attempts_rejected(sql: str) -> None:
    with pytest.raises(SQLGuardError):
        assert_read_only(sql)


# ---------------------------------------------------------------------------
# Misc edge cases
# ---------------------------------------------------------------------------

def test_empty_query_rejected() -> None:
    with pytest.raises(SQLGuardError):
        assert_read_only("")


def test_whitespace_only_query_rejected() -> None:
    with pytest.raises(SQLGuardError):
        assert_read_only("   \n\t  ")


def test_only_comment_query_rejected() -> None:
    with pytest.raises(SQLGuardError):
        assert_read_only("-- just a comment, no statement")


def test_non_string_input_rejected() -> None:
    with pytest.raises(SQLGuardError):
        assert_read_only(None)  # type: ignore[arg-type]


def test_forbidden_keyword_as_substring_of_identifier_is_allowed() -> None:
    # "Updated_At" contains "update" as a substring but is just a column
    # name; a naive substring check would wrongly reject this.
    assert_read_only("SELECT Updated_At, Created_By FROM Sample.Person")


def test_forbidden_keyword_inside_string_literal_is_allowed() -> None:
    assert_read_only(
        "SELECT * FROM Sample.Log WHERE Message = 'insert failed, please retry'"
    )

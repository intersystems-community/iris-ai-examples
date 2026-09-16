import pytest

from shared.iris_jdbc import (
    InvalidIrisTarget,
    build_jdbc_url,
    build_pgwire_dsn,
    build_pgwire_url,
    escape_sql_literal,
    validate_identifier,
)


def test_build_jdbc_url_matches_documented_form():
    assert build_jdbc_url("iris.example.com", 1972, "HSFHIR") == "jdbc:IRIS://iris.example.com:1972/HSFHIR"


def test_build_jdbc_url_rejects_bad_port():
    with pytest.raises(InvalidIrisTarget):
        build_jdbc_url("iris.example.com", 70000, "HSFHIR")


def test_build_jdbc_url_rejects_zero_port():
    with pytest.raises(InvalidIrisTarget):
        build_jdbc_url("iris.example.com", 0, "HSFHIR")


def test_build_jdbc_url_rejects_unsafe_host():
    with pytest.raises(InvalidIrisTarget):
        build_jdbc_url("iris.example.com'; DROP TABLE x; --", 1972, "HSFHIR")


def test_build_jdbc_url_rejects_bad_namespace():
    with pytest.raises(InvalidIrisTarget):
        build_jdbc_url("iris.example.com", 1972, "bad namespace")


def test_build_pgwire_dsn():
    dsn = build_pgwire_dsn("localhost", 5432, "USER", "_SYSTEM", "SYS")
    assert dsn == "host=localhost port=5432 dbname=USER user=_SYSTEM password=SYS"


def test_build_pgwire_url():
    url = build_pgwire_url("localhost", 5432, "USER", "_SYSTEM", "SYS")
    assert url == "postgresql://_SYSTEM:SYS@localhost:5432/USER"


def test_escape_sql_literal_doubles_single_quote():
    assert escape_sql_literal("O'Brien") == "O''Brien"


def test_escape_sql_literal_noop_on_plain_string():
    assert escape_sql_literal("plain") == "plain"


def test_validate_identifier_accepts_valid_names():
    assert validate_identifier("iris_federation") == "iris_federation"
    assert validate_identifier("_leading_underscore") == "_leading_underscore"


@pytest.mark.parametrize(
    "bad_name",
    ["1starts_with_digit", "has space", "has-dash", "has'quote", "", "has;semicolon"],
)
def test_validate_identifier_rejects_invalid_names(bad_name):
    with pytest.raises(InvalidIrisTarget):
        validate_identifier(bad_name)

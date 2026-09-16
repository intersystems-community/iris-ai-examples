from __future__ import annotations

import pytest

from mcp_iris.catalog import describe_table_sql, list_schemas_sql, list_tables_sql
from mcp_iris.identifiers import InvalidIdentifierError


def test_list_schemas_sql_has_no_params() -> None:
    sql, params = list_schemas_sql()
    assert "INFORMATION_SCHEMA.SCHEMATA" in sql
    assert params == ()


def test_list_tables_sql_without_schema_has_no_params() -> None:
    sql, params = list_tables_sql(None)
    assert "INFORMATION_SCHEMA.TABLES" in sql
    assert params == ()


def test_list_tables_sql_with_schema_binds_it_as_a_parameter() -> None:
    sql, params = list_tables_sql("Sample")
    assert "?" in sql
    assert params == ("Sample",)
    # The schema name must never be string-interpolated into the SQL text.
    assert "Sample" not in sql


def test_list_tables_sql_rejects_malicious_schema_name() -> None:
    with pytest.raises(InvalidIdentifierError):
        list_tables_sql("Sample; DROP TABLE Foo")


def test_describe_table_sql_binds_schema_and_table() -> None:
    sql, params = describe_table_sql("Sample", "Person")
    assert params == ("Sample", "Person")
    assert "Sample" not in sql
    assert "Person" not in sql
    assert "INFORMATION_SCHEMA.COLUMNS" in sql


@pytest.mark.parametrize(
    "schema,table",
    [
        ("Sample; DROP TABLE Foo", "Person"),
        ("Sample", "Person; DROP TABLE Foo"),
        ("", "Person"),
        ("Sample", ""),
        ("Sample'--", "Person"),
    ],
)
def test_describe_table_sql_rejects_malicious_identifiers(schema: str, table: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        describe_table_sql(schema, table)

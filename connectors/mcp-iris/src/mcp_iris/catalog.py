"""SQL builders for the catalog tools (list schemas, list tables, describe
a table), built on ``INFORMATION_SCHEMA`` -- the ANSI-standard metadata
views IRIS documents at
https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=INFORMATION.SCHEMA.TABLES
and
https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=INFORMATION.SCHEMA.COLUMNS

``INFORMATION_SCHEMA.COLUMNS.COLUMN_NAME`` and ``.TABLE_NAME`` are directly
confirmed by an InterSystems-published example query in that documentation.
``INFORMATION_SCHEMA.SCHEMATA`` and the remaining ANSI column names used
here (``TABLE_SCHEMA``, ``TABLE_TYPE``, ``DATA_TYPE``, ``IS_NULLABLE``,
``ORDINAL_POSITION``, ``COLUMN_DEFAULT``) follow the same
``INFORMATION.SCHEMA.*`` class-naming pattern IRIS uses for the two
confirmed views, but were not independently confirmed against a live
namespace in this environment -- see STATUS.md's UNVERIFIED section.

These functions only build parameterized SQL strings; they never execute
anything themselves, and every identifier that is *not* a bind parameter
(there are none here -- schema/table names are always passed as bind
parameters, never string-interpolated) goes through
``identifiers.validate_identifier`` at the tool layer before it reaches this
module at all.
"""

from __future__ import annotations

from .identifiers import validate_identifier

__all__ = ["list_schemas_sql", "list_tables_sql", "describe_table_sql"]


def list_schemas_sql() -> tuple[str, tuple[()]]:
    sql = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME"
    return sql, ()


def list_tables_sql(schema: str | None) -> tuple[str, tuple[str, ...]]:
    if schema is None:
        sql = (
            "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
            "FROM INFORMATION_SCHEMA.TABLES "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        return sql, ()
    validate_identifier(schema)
    sql = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
        "FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = ? "
        "ORDER BY TABLE_NAME"
    )
    return sql, (schema,)


def describe_table_sql(schema: str, table: str) -> tuple[str, tuple[str, str]]:
    validate_identifier(schema)
    validate_identifier(table)
    sql = (
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
        "ORDINAL_POSITION "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
        "ORDER BY ORDINAL_POSITION"
    )
    return sql, (schema, table)

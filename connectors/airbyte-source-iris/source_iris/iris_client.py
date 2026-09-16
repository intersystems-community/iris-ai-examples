#
# source-iris: IRIS catalog discovery and row access on top of the DB-API boundary.
#
# Every method here takes a `DBAPIConnection` (see db.py) so tests can drive it with a
# fake connection instead of a live IRIS instance. No method builds a SQL string by
# interpolating a schema/table/column name directly — all identifiers are routed
# through `type_mapping.quote_ident` / `quote_qualified`, and all values are bound as
# DB-API parameters (`?`, the driver's documented paramstyle — see
# https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=BPYDBAPI_refapi,
# and `iris.dbapi.paramstyle == "qmark"`, confirmed in STATUS.md).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .db import DBAPIConnection
from .type_mapping import is_lob_type, quote_ident, quote_qualified

# Default set of IRIS system schemas excluded from discovery unless the user opts in.
# These hold %-package classes, security/audit tables, etc. that are never user data.
# (INFORMATION_SCHEMA itself is filtered out too, since it is metadata about metadata.)
DEFAULT_EXCLUDED_SCHEMAS = frozenset(
    {
        "INFORMATION_SCHEMA",
        "%SYS",
        "Ens",
        "Ens_Util",
        "EnsLib",
        "EnsPortal",
        "HS",
        "HSLIB",
        "Security",
        "Sys",
        "SYS",
        "%CSP",
        "%Monitor",
    }
)

FETCH_BATCH_SIZE = 1000


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int
    is_primary_key: bool = False
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    character_maximum_length: Optional[int] = None

    @property
    def is_lob(self) -> bool:
        return is_lob_type(self.data_type)


@dataclass(frozen=True)
class TableMeta:
    schema: str
    name: str
    table_type: str
    columns: List[ColumnMeta] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def primary_key(self) -> List[str]:
        return [c.name for c in self.columns if c.is_primary_key]


class IrisClient:
    """Thin, injectable client. Construct with any object satisfying DBAPIConnection."""

    def __init__(self, connection: DBAPIConnection):
        self._connection = connection

    # -- connectivity --------------------------------------------------------------

    def test_connection(self) -> None:
        """Raises on failure. Used by Source.check_connection."""
        cursor = self._connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchall()
        finally:
            cursor.close()

    def close(self) -> None:
        self._connection.close()

    # -- discovery --------------------------------------------------------------

    def list_tables(self, schemas: Optional[Sequence[str]] = None) -> List[TableMeta]:
        """
        Discover tables (and their columns) via INFORMATION_SCHEMA, per
        https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=INFORMATION.SCHEMA.TABLES
        and .../CLASSNAME=INFORMATION.SCHEMA.COLUMNS.

        If `schemas` is given, only those schemas are considered. Otherwise every
        schema not in DEFAULT_EXCLUDED_SCHEMAS is considered.
        """
        tables = self._list_table_rows(schemas)
        for table in tables:
            table.columns.extend(self._list_columns(table.schema, table.name))
        return tables

    def _list_table_rows(self, schemas: Optional[Sequence[str]]) -> List[TableMeta]:
        cursor = self._connection.cursor()
        try:
            if schemas:
                placeholders = ", ".join("?" for _ in schemas)
                sql = (
                    "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                    "FROM INFORMATION_SCHEMA.TABLES "
                    f"WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA IN ({placeholders}) "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
                )
                cursor.execute(sql, list(schemas))
            else:
                cursor.execute(
                    "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                    "FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_TYPE = 'BASE TABLE' "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
                )
            rows = cursor.fetchall()
        finally:
            cursor.close()

        result = []
        for schema, name, table_type in rows:
            if schemas is None and schema in DEFAULT_EXCLUDED_SCHEMAS:
                continue
            # TableMeta is a frozen dataclass, but `columns` defaults to a fresh mutable
            # list per instance; frozen only blocks *reassigning* the attribute, so
            # `_list_columns`'s caller can still `.extend()` it in place below.
            result.append(TableMeta(schema=schema, name=name, table_type=table_type))
        return result

    def _list_columns(self, schema: str, table: str) -> List[ColumnMeta]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION, "
                "PRIMARY_KEY, NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
                "ORDER BY ORDINAL_POSITION",
                [schema, table],
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()

        columns = []
        for (
            col_name,
            data_type,
            is_nullable,
            ordinal_position,
            primary_key,
            numeric_precision,
            numeric_scale,
            char_max_len,
        ) in rows:
            columns.append(
                ColumnMeta(
                    name=col_name,
                    data_type=data_type,
                    is_nullable=str(is_nullable).upper() != "NO",
                    ordinal_position=ordinal_position,
                    is_primary_key=str(primary_key).upper() == "YES",
                    numeric_precision=numeric_precision,
                    numeric_scale=numeric_scale,
                    character_maximum_length=char_max_len,
                )
            )
        return columns

    # -- reading --------------------------------------------------------------

    def read_full_refresh(
        self, schema: str, table: str, column_names: Sequence[str]
    ) -> Iterator[Dict[str, Any]]:
        """Yield every row of `schema.table` as a dict, selecting only `column_names`."""
        select_list = ", ".join(quote_ident(c) for c in column_names)
        sql = f"SELECT {select_list} FROM {quote_qualified(schema, table)}"
        yield from self._execute_and_stream(sql, [], column_names)

    def read_incremental(
        self,
        schema: str,
        table: str,
        column_names: Sequence[str],
        cursor_field: str,
        cursor_value: Optional[Any],
    ) -> Iterator[Dict[str, Any]]:
        """
        Yield rows of `schema.table` with `cursor_field` strictly greater than
        `cursor_value` (or every row, if `cursor_value` is None, i.e. first sync),
        ordered ascending by the cursor so the caller can checkpoint incrementally.

        `cursor_value` is always passed as a bound parameter (`?`), never interpolated.
        """
        select_list = ", ".join(quote_ident(c) for c in column_names)
        quoted_cursor = quote_ident(cursor_field)
        sql = f"SELECT {select_list} FROM {quote_qualified(schema, table)}"
        params: List[Any] = []
        if cursor_value is not None:
            sql += f" WHERE {quoted_cursor} > ?"
            params.append(cursor_value)
        sql += f" ORDER BY {quoted_cursor} ASC"
        yield from self._execute_and_stream(sql, params, column_names)

    def _execute_and_stream(
        self, sql: str, params: Sequence[Any], column_names: Sequence[str]
    ) -> Iterator[Dict[str, Any]]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, params)
            while True:
                batch = cursor.fetchmany(FETCH_BATCH_SIZE)
                if not batch:
                    break
                for row in batch:
                    yield dict(zip(column_names, row))
        finally:
            cursor.close()

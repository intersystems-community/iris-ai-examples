"""Schema discovery against IRIS `INFORMATION_SCHEMA`.

Column/view names used here are IRIS-specific, not assumed ANSI defaults --
in particular `INFORMATION_SCHEMA.COLUMNS.PRIMARY_KEY` (a `YES`/`NO` flag
column IRIS adds directly to `COLUMNS`, unlike the ANSI-standard approach of
joining `KEY_COLUMN_USAGE`), and `INFORMATION_SCHEMA.TABLES.TABLE_TYPE =
'BASE TABLE'` to exclude views/system tables. These were confirmed against
InterSystems' own documentation and Developer Community posts (see
README.md's "IRIS connectivity facts" section for citations); they have not
been confirmed against a live IRIS instance in this environment (no running
IRIS -- see STATUS.md).
"""

from typing import Callable, List, Optional

from iris_connector.db import DBConnection
from iris_connector.type_mapping import map_iris_type

TABLES_SQL = """
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME
"""

COLUMNS_SQL = """
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION,
       NUMERIC_SCALE, IS_NULLABLE, PRIMARY_KEY
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
ORDER BY ORDINAL_POSITION
"""


class TableColumns:
    """The syncable subset of one table's columns, in source order."""

    __slots__ = ("table_name", "column_names", "fivetran_types", "primary_key")

    def __init__(
        self,
        table_name: str,
        column_names: List[str],
        fivetran_types: dict,
        primary_key: List[str],
    ):
        self.table_name = table_name
        self.column_names = column_names  # ordered, syncable-only
        self.fivetran_types = fivetran_types  # column_name -> Fivetran type
        self.primary_key = primary_key


def list_tables(connection: DBConnection, db_schema: str) -> List[str]:
    """Returns base-table names in `db_schema`, sorted."""
    cursor = connection.cursor()
    try:
        cursor.execute(TABLES_SQL, (db_schema,))
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


def describe_table(
    connection: DBConnection,
    db_schema: str,
    table_name: str,
    warn: Optional[Callable[[str], None]] = None,
) -> Optional[TableColumns]:
    """Discovers one table's syncable columns, types, and primary key.

    Returns `None` if the table has no syncable columns left after type
    mapping drops (see `type_mapping.DROPPED_TYPES`) -- e.g. an
    all-%Stream table -- in which case the caller should skip it (and
    `warn`, if given, has already recorded why).
    """
    cursor = connection.cursor()
    try:
        cursor.execute(COLUMNS_SQL, (db_schema, table_name))
        rows = cursor.fetchall()
    finally:
        cursor.close()

    column_names: List[str] = []
    fivetran_types: dict = {}
    primary_key: List[str] = []

    for row in rows:
        column_name, data_type, char_len, num_precision, num_scale, is_nullable, is_pk = row
        mapped = map_iris_type(
            data_type,
            char_len,
            num_precision,
            num_scale,
            warn=warn,
            context=f"{table_name}.{column_name}",
        )
        if mapped is None:
            continue
        column_names.append(column_name)
        fivetran_types[column_name] = mapped
        if str(is_pk).strip().upper() == "YES":
            primary_key.append(column_name)

    if not column_names:
        if warn:
            warn(f"{table_name}: no syncable columns after type mapping; table skipped.")
        return None

    return TableColumns(table_name, column_names, fivetran_types, primary_key)


def discover_schema(
    connection: DBConnection,
    db_schema: str,
    table_allowlist: Optional[List[str]] = None,
    warn: Optional[Callable[[str], None]] = None,
) -> List[TableColumns]:
    """Discovers every syncable base table in `db_schema` (or just the
    tables in `table_allowlist`, if given), in table-name order.
    """
    table_names = list_tables(connection, db_schema)
    if table_allowlist:
        missing = sorted(set(table_allowlist) - set(table_names))
        if missing:
            if warn:
                warn(
                    "configuration.tables names table(s) not found in "
                    f"{db_schema}: {', '.join(missing)}."
                )
        table_names = [name for name in table_names if name in table_allowlist]

    tables = []
    for table_name in table_names:
        described = describe_table(connection, db_schema, table_name, warn=warn)
        if described is not None:
            tables.append(described)
    return tables


def build_fivetran_schema(tables: List[TableColumns]) -> List[dict]:
    """Converts discovered tables into the list-of-dicts shape
    `fivetran_connector_sdk.Connector`'s `schema()` return value must be
    (per `connector_helper.process_tables`): each entry is
    `{"table": str, "primary_key": [str, ...], "columns": {str: type}}`,
    with `primary_key` omitted when the table has none.
    """
    schema_defs = []
    for table in tables:
        entry: dict = {
            "table": table.table_name,
            "columns": {name: table.fivetran_types[name] for name in table.column_names},
        }
        if table.primary_key:
            entry["primary_key"] = table.primary_key
        schema_defs.append(entry)
    return schema_defs

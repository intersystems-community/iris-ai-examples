"""A fake DB-API connection that drives the whole connector without a real
IRIS instance -- used by the `pytest` suite, and (via `demo_connection()`)
by the local `fivetran debug` walkthrough in this directory.

It implements exactly the `db.DBConnection` / `db.DBCursor` structural
protocols, plus enough of a tiny SQL interpreter to satisfy the *specific,
fixed* set of query shapes `catalog.py` and `sync.py` generate:

  - `SELECT ... FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ? AND
     TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME`
  - `SELECT ... FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND
     TABLE_NAME = ? ORDER BY ORDINAL_POSITION`
  - `SELECT <cols> FROM <schema>.<table> [WHERE <col> (>=|>) ?] [ORDER BY <col>]`

This is deliberately *not* a general SQL engine -- it is a test double
scoped to this connector's own query templates, in the same spirit as
`careconnect-sdoh/evals`'s provider-agnostic fakes.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class FakeColumn:
    """One `INFORMATION_SCHEMA.COLUMNS` row, pre-shaped for the fake."""

    name: str
    data_type: str
    character_maximum_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    is_nullable: str = "YES"
    primary_key: bool = False

    def as_row(self) -> Tuple:
        return (
            self.name,
            self.data_type,
            self.character_maximum_length,
            self.numeric_precision,
            self.numeric_scale,
            self.is_nullable,
            "YES" if self.primary_key else "NO",
        )


@dataclass
class FakeTable:
    """One base table: its column metadata plus its current row data."""

    name: str
    columns: List[FakeColumn]
    rows: List[Dict[str, Any]] = field(default_factory=list)

    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


class FakeCursor:
    """Implements `db.DBCursor` against a `FakeConnection`'s in-memory tables."""

    _TABLES_QUERY = re.compile(r"FROM\s+INFORMATION_SCHEMA\.TABLES", re.IGNORECASE)
    _COLUMNS_QUERY = re.compile(r"FROM\s+INFORMATION_SCHEMA\.COLUMNS", re.IGNORECASE)
    _SELECT_QUERY = re.compile(
        r"SELECT\s+(?P<cols>.+?)\s+FROM\s+\S+\.(?P<table>\w+)"
        r"(?:\s+WHERE\s+(?P<where_col>\w+)\s*(?P<op>>=|>)\s*\?)?"
        r"(?:\s+ORDER\s+BY\s+(?P<order_col>\w+))?\s*$",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, connection: "FakeConnection"):
        self._connection = connection
        self.description: Optional[Sequence[Sequence[Any]]] = None
        self._result_rows: List[Tuple] = []
        self._offset = 0
        self.closed = False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        if self.closed:
            raise RuntimeError("cursor is closed")
        sql_normalized = " ".join(sql.split())

        if self._TABLES_QUERY.search(sql_normalized):
            self._execute_list_tables(params)
            return
        if self._COLUMNS_QUERY.search(sql_normalized):
            self._execute_describe_columns(params)
            return

        match = self._SELECT_QUERY.search(sql_normalized)
        if not match:
            raise NotImplementedError(f"FakeCursor cannot interpret SQL: {sql!r}")
        self._execute_select(match, params)

    def _execute_list_tables(self, params: Sequence[Any]) -> None:
        # params = (db_schema,); the fake models a single flat namespace, so
        # every registered table is treated as living in that schema.
        names = sorted(self._connection.tables.keys())
        self._result_rows = [(name,) for name in names]
        self.description = [("TABLE_NAME",)]
        self._offset = 0

    def _execute_describe_columns(self, params: Sequence[Any]) -> None:
        _db_schema, table_name = params
        table = self._connection.tables.get(table_name)
        rows = [col.as_row() for col in table.columns] if table else []
        self._result_rows = rows
        self.description = [
            ("COLUMN_NAME",), ("DATA_TYPE",), ("CHARACTER_MAXIMUM_LENGTH",),
            ("NUMERIC_PRECISION",), ("NUMERIC_SCALE",), ("IS_NULLABLE",), ("PRIMARY_KEY",),
        ]
        self._offset = 0

    def _execute_select(self, match: "re.Match", params: Sequence[Any]) -> None:
        table_name = match.group("table")
        table = self._connection.tables[table_name]
        col_names = [c.strip() for c in match.group("cols").split(",")]

        rows = list(table.rows)

        where_col = match.group("where_col")
        op = match.group("op")
        if where_col:
            bound = params[0]
            if op == ">=":
                rows = [r for r in rows if r[where_col] >= bound]
            else:
                rows = [r for r in rows if r[where_col] > bound]

        order_col = match.group("order_col")
        if order_col:
            rows = sorted(rows, key=lambda r: r[order_col])

        self._result_rows = [tuple(r[c] for c in col_names) for r in rows]
        self.description = [(c,) for c in col_names]
        self._offset = 0

    def fetchmany(self, size: int) -> List[Tuple]:
        chunk = self._result_rows[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def fetchall(self) -> List[Tuple]:
        chunk = self._result_rows[self._offset :]
        self._offset = len(self._result_rows)
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    """Implements `db.DBConnection` over a fixed set of `FakeTable`s."""

    def __init__(self, tables: Optional[Dict[str, FakeTable]] = None):
        self.tables: Dict[str, FakeTable] = tables or {}
        self.closed = False
        self.cursors_opened = 0

    def cursor(self) -> FakeCursor:
        self.cursors_opened += 1
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True

    def add_table(self, table: FakeTable) -> None:
        self.tables[table.name] = table


def demo_connection() -> FakeConnection:
    """A small, realistic fixture: two tables exercising every mapped IRIS
    type family plus one dropped-type column, used by `connector.py` when
    `configuration["driver"] == "fake"` (local `fivetran debug` walkthrough
    only -- never selected in production; see README.md/STATUS.md) and
    reused by several tests for an end-to-end sanity check.
    """
    patient = FakeTable(
        name="PATIENT",
        columns=[
            FakeColumn("PATIENT_ID", "BIGINT", primary_key=True),
            FakeColumn("NAME", "VARCHAR", character_maximum_length=100),
            FakeColumn("BIRTH_DATE", "DATE"),
            FakeColumn("LAST_UPDATED", "TIMESTAMP"),
            FakeColumn("HEIGHT_CM", "NUMERIC", numeric_precision=5, numeric_scale=1),
            FakeColumn("IS_ACTIVE", "BIT"),
            FakeColumn("CHART_NOTE", "LONGVARCHAR"),  # dropped: %Stream.GlobalCharacter
        ],
        rows=[
            {
                "PATIENT_ID": 1, "NAME": "Ada Lovelace", "BIRTH_DATE": "1815-12-10",
                "LAST_UPDATED": "2026-01-01 08:00:00", "HEIGHT_CM": "163.0",
                "IS_ACTIVE": 1, "CHART_NOTE": "(stream not modeled)",
            },
            {
                "PATIENT_ID": 2, "NAME": "Alan Turing", "BIRTH_DATE": "1912-06-23",
                "LAST_UPDATED": "2026-01-02 09:30:00", "HEIGHT_CM": "179.5",
                "IS_ACTIVE": 1, "CHART_NOTE": "(stream not modeled)",
            },
        ],
    )
    encounter = FakeTable(
        name="ENCOUNTER",
        columns=[
            FakeColumn("ENCOUNTER_ID", "INTEGER", primary_key=True),
            FakeColumn("PATIENT_ID", "BIGINT"),
            FakeColumn("VISIT_AT", "POSIXTIME"),
            FakeColumn("NOTE", "VARCHAR", character_maximum_length=255),
        ],
        rows=[
            {"ENCOUNTER_ID": 1, "PATIENT_ID": 1, "VISIT_AT": "2026-02-01 10:00:00.000000", "NOTE": "annual checkup"},
            {"ENCOUNTER_ID": 2, "PATIENT_ID": 2, "VISIT_AT": "2026-02-03 14:15:00.000000", "NOTE": "follow-up"},
        ],
    )
    return FakeConnection({"PATIENT": patient, "ENCOUNTER": encounter})

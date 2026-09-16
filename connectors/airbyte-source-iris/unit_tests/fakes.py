#
# A fake, in-memory DB-API connection satisfying `source_iris.db.DBAPIConnection` /
# `DBAPICursor`. Every test in this directory drives the connector through this fake
# instead of a live IRIS instance — there is no running IRIS and no Docker daemon in
# this environment (see STATUS.md), so this fake is the only thing that can possibly
# exercise source.py/streams.py/iris_client.py end to end.
#
# It understands exactly the shapes of SQL that source_iris.iris_client.IrisClient
# generates: "SELECT 1", the two INFORMATION_SCHEMA queries, and
# `SELECT <cols> FROM "schema"."table" [WHERE "cursor" > ?] [ORDER BY "cursor" ASC]`.
# It is not a general SQL engine, and deliberately raises AssertionError on anything
# else so a change to the generated SQL shape fails loudly in tests rather than
# silently returning nothing.

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_SELECT_RE = re.compile(
    r'SELECT\s+(?P<cols>.*?)\s+FROM\s+"(?P<schema>[^"]+)"\."(?P<table>[^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
_WHERE_RE = re.compile(r'WHERE\s+"(?P<col>[^"]+)"\s*>\s*\?', re.IGNORECASE)
_ORDER_RE = re.compile(r'ORDER BY\s+"(?P<col>[^"]+)"', re.IGNORECASE)


class FakeCursor:
    def __init__(self, connection: "FakeIrisConnection"):
        self._connection = connection
        self._rows: List[Tuple[Any, ...]] = []
        self.description: Optional[Sequence[Sequence[Any]]] = None
        self.closed = False

    def execute(self, operation: str, parameters: Sequence[Any] = ()) -> Any:
        self._connection.executed_statements.append((operation, list(parameters)))
        self._rows = list(self._connection.dispatch(operation, list(parameters)))
        self.description = [(f"col{i}",) for i in range(len(self._rows[0]))] if self._rows else None
        return self

    def fetchmany(self, size: int) -> List[Tuple[Any, ...]]:
        batch, self._rows = self._rows[:size], self._rows[size:]
        return batch

    def fetchall(self) -> List[Tuple[Any, ...]]:
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        if not self._rows:
            return None
        return self._rows.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeIrisConnection:
    """
    Construct with:
      tables_catalog: list of (TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE) tuples.
      columns_catalog: dict[(schema, table)] -> list of
          (COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION, PRIMARY_KEY,
           NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH) tuples,
          matching the exact SELECT list of IrisClient._list_columns.
      table_data: dict[(schema, table)] -> list of row dicts, keyed by column name.
      fail_test_query: if True, "SELECT 1" (used by check_connection) raises.
    """

    def __init__(
        self,
        tables_catalog: Optional[List[Tuple[Any, ...]]] = None,
        columns_catalog: Optional[Dict[Tuple[str, str], List[Tuple[Any, ...]]]] = None,
        table_data: Optional[Dict[Tuple[str, str], List[Dict[str, Any]]]] = None,
        fail_test_query: bool = False,
    ):
        self.tables_catalog = tables_catalog or []
        self.columns_catalog = columns_catalog or {}
        self.table_data = table_data or {}
        self.fail_test_query = fail_test_query
        self.executed_statements: List[Tuple[str, List[Any]]] = []
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True

    def dispatch(self, sql: str, params: List[Any]) -> List[Tuple[Any, ...]]:
        stripped = sql.strip()

        if stripped == "SELECT 1":
            if self.fail_test_query:
                raise RuntimeError("simulated IRIS connectivity failure")
            return [(1,)]

        if "INFORMATION_SCHEMA.TABLES" in sql:
            rows = list(self.tables_catalog)
            if "TABLE_SCHEMA IN" in sql:
                allowed = set(params)
                rows = [r for r in rows if r[0] in allowed]
            return sorted(rows, key=lambda r: (r[0], r[1]))

        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            schema, table = params
            return list(self.columns_catalog.get((schema, table), []))

        match = _SELECT_RE.search(sql)
        if not match:
            raise AssertionError(f"FakeIrisConnection cannot handle this SQL shape: {sql!r}")

        schema, table = match.group("schema"), match.group("table")
        columns = [c.strip().strip('"') for c in match.group("cols").split(",")]
        rows = list(self.table_data.get((schema, table), []))

        where_match = _WHERE_RE.search(sql)
        if where_match:
            col, threshold = where_match.group("col"), params[0]
            rows = [r for r in rows if r[col] > threshold]

        order_match = _ORDER_RE.search(sql)
        if order_match:
            order_col = order_match.group("col")
            rows = sorted(rows, key=lambda r: r[order_col])

        return [tuple(r[c] for c in columns) for r in rows]

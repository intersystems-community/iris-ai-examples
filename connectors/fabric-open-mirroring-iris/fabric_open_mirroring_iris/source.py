"""Abstraction over an IRIS table used as a change source.

Production code talks to IRIS through the standard IRIS DB-API driver
(``pip install intersystems-irispython`` -> ``import iris``; see
https://docs.intersystems.com/ for `iris.connect`). Tests never touch a real
IRIS instance (none is available in this environment) -- they run entirely
against ``FakeIrisSource``, an in-memory stand-in that implements the same
``IrisSource`` protocol.

Change-data-capture caveat (read this before wiring to production IRIS):
Plain IRIS SQL has no generic, built-in row-level change feed comparable to
SQL Server CDC or a database transaction log reader. This module supports
two concrete, IRIS-SQL-only strategies for detecting changes, both of which
are *application-level conventions* the source table must already follow --
they are not something IRIS provides automatically:

  1. Watermark-column strategy: the table has a monotonically increasing
     column (an identity/sequence, or a maintained "%%LastModified"
     timestamp). Rows with watermark > last-seen-watermark are read as
     inserts/updates. This cannot see hard deletes.
  2. Soft-delete convention: the table additionally carries a boolean/flag
     column (e.g. "IsDeleted") the application sets instead of issuing SQL
     DELETE. Rows where that flag transitions to true are emitted as delete
     changes.

True hard-delete capture requires either building on IRIS's underlying
journal (see https://docs.intersystems.com/ "Journaling" -- not exposed via
plain SQL and out of scope for this connector) or a trigger-maintained
change-log table. Both are documented as HUMAN ACTIONS REQUIRED / future
work in STATUS.md and PUBLISHING.md; this connector does not implement
journal mining.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Literal, Optional, Protocol

from .iris_types import ColumnDef

ChangeOp = Literal["insert", "update", "delete"]


@dataclass(frozen=True)
class ChangeRecord:
    op: ChangeOp
    row: dict[str, Any]  # full row for insert/update; at least key columns for delete


@dataclass(frozen=True)
class ChangeBatch:
    records: list[ChangeRecord]
    next_token: Optional[str]


class IrisSource(Protocol):
    """What the publisher needs from an IRIS table.

    Implemented by `FakeIrisSource` (tests) and `IrisDbApiSource`
    (production, real `iris` DB-API driver).
    """

    def get_table_schema(self, table_name: str) -> list[ColumnDef]: ...

    def fetch_snapshot(
        self, table_name: str, *, offset: int = 0, limit: Optional[int] = None
    ) -> Iterator[dict[str, Any]]:
        """Yield rows for the initial load, in a stable order, starting at
        `offset` (row-count based resume position) so a crashed snapshot can
        resume without re-reading rows already durably written."""
        ...

    def fetch_changes(self, table_name: str, since_token: Optional[str]) -> ChangeBatch: ...


class FakeIrisSource:
    """In-memory `IrisSource` used by tests.

    Holds a fixed table schema, a list of "committed" snapshot rows, and an
    append-only change log. Tests call `apply_insert` / `apply_update` /
    `apply_delete` to script a sequence of source-side changes and then
    exercise the publisher against them.
    """

    def __init__(self, schema: list[ColumnDef], key_columns: list[str]):
        self._schema = schema
        self._key_columns = key_columns
        self._snapshot_rows: list[dict[str, Any]] = []
        self._change_log: list[ChangeRecord] = []

    # -- test-side scripting API -------------------------------------------------
    def seed_snapshot(self, rows: Iterable[dict[str, Any]]) -> None:
        self._snapshot_rows = list(rows)

    def apply_insert(self, row: dict[str, Any]) -> None:
        self._change_log.append(ChangeRecord("insert", dict(row)))

    def apply_update(self, row: dict[str, Any]) -> None:
        self._change_log.append(ChangeRecord("update", dict(row)))

    def apply_delete(self, key: dict[str, Any]) -> None:
        self._change_log.append(ChangeRecord("delete", dict(key)))

    # -- IrisSource protocol ------------------------------------------------------
    def get_table_schema(self, table_name: str) -> list[ColumnDef]:
        return list(self._schema)

    def fetch_snapshot(
        self, table_name: str, *, offset: int = 0, limit: Optional[int] = None
    ) -> Iterator[dict[str, Any]]:
        rows = self._snapshot_rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        yield from rows

    def fetch_changes(self, table_name: str, since_token: Optional[str]) -> ChangeBatch:
        start = int(since_token) if since_token else 0
        pending = self._change_log[start:]
        next_token = str(len(self._change_log))
        return ChangeBatch(records=pending, next_token=next_token)


# ---------------------------------------------------------------------------
# Production adapter. Not exercised by the test suite (no live IRIS in this
# environment) -- included so the abstraction has a real, documented
# implementation, and so its SQL is reviewable.
# ---------------------------------------------------------------------------


@dataclass
class ChangeTrackingConfig:
    """Declares which application-level CDC convention (see module docstring)
    a given table follows."""

    watermark_column: str
    soft_delete_column: Optional[str] = None
    soft_delete_true_value: Any = 1


class IrisDbApiSource:
    """Real IRIS table access via the `iris` DB-API driver
    (`pip install intersystems-irispython`).

    Connection is via `iris.connect(hostname, port, namespace, username,
    password)` per
    https://docs.intersystems.com/irislatest/csp/documatic/%25CSP.Documatic.cls?LIBRARY=%25SYS&CLASSNAME=%25SQL.Manager (Python DB-API docs)
    and the connectors/README.md table of IRIS connectivity facts for this
    repo (port 1972 superserver, DB-API package `intersystems-irispython`).
    """

    def __init__(self, connection: Any, change_tracking: dict[str, ChangeTrackingConfig]):
        self._conn = connection
        self._change_tracking = change_tracking

    def get_table_schema(self, table_name: str) -> list[ColumnDef]:
        schema_name, bare_name = _split_table_name(table_name)
        sql = (
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, NUMERIC_PRECISION, "
            "NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION"
        )
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, [schema_name, bare_name])
            rows = cursor.fetchall()
        finally:
            cursor.close()
        columns = []
        for name, data_type, is_nullable, precision, scale, max_len in rows:
            columns.append(
                ColumnDef(
                    name=name,
                    iris_type=str(data_type),
                    nullable=str(is_nullable).upper() != "NO",
                    precision=precision,
                    scale=scale,
                    max_length=max_len,
                )
            )
        return columns

    def fetch_snapshot(
        self, table_name: str, *, offset: int = 0, limit: Optional[int] = None
    ) -> Iterator[dict[str, Any]]:
        cursor = self._conn.cursor()
        try:
            # IRIS SQL: TOP is a prefix; OFFSET/FETCH is standard SQL-92 and
            # supported for stable pagination when a deterministic ORDER BY
            # is present.
            sql = f"SELECT * FROM {table_name} ORDER BY 1 OFFSET ? ROWS"
            params: list[Any] = [offset]
            if limit is not None:
                sql += " FETCH NEXT ? ROWS ONLY"
                params.append(limit)
            cursor.execute(sql, params)
            col_names = [d[0] for d in cursor.description]
            for row in cursor.fetchall():
                yield dict(zip(col_names, row))
        finally:
            cursor.close()

    def fetch_changes(self, table_name: str, since_token: Optional[str]) -> ChangeBatch:
        tracking = self._change_tracking.get(table_name)
        if tracking is None:
            raise ValueError(
                f"No ChangeTrackingConfig registered for table '{table_name}'. "
                "See module docstring: IRIS SQL has no generic CDC feed, so a "
                "watermark/soft-delete convention must be declared explicitly."
            )
        last_watermark = since_token or "0"
        cursor = self._conn.cursor()
        try:
            sql = (
                f"SELECT * FROM {table_name} WHERE {tracking.watermark_column} > ? "
                f"ORDER BY {tracking.watermark_column}"
            )
            cursor.execute(sql, [last_watermark])
            col_names = [d[0] for d in cursor.description]
            records = []
            max_watermark = last_watermark
            for row in cursor.fetchall():
                row_dict = dict(zip(col_names, row))
                is_delete = (
                    tracking.soft_delete_column is not None
                    and row_dict.get(tracking.soft_delete_column) == tracking.soft_delete_true_value
                )
                op: ChangeOp = "delete" if is_delete else "update"
                records.append(ChangeRecord(op, row_dict))
                wm = row_dict[tracking.watermark_column]
                if str(wm) > str(max_watermark):
                    max_watermark = wm
            return ChangeBatch(records=records, next_token=str(max_watermark))
        finally:
            cursor.close()


def _split_table_name(table_name: str) -> tuple[str, str]:
    if "." in table_name:
        schema, _, bare = table_name.partition(".")
        return schema, bare
    return "SQLUser", table_name

"""`update()` orchestration: per-table full-refresh or incremental sync,
upsert emission, and checkpointing.

State shape (all JSON-serializable; this is exactly what Fivetran persists
and hands back on the next sync):

    {
      "tables": {
        "<table_name>": {
          # Incremental tables (listed in configuration.cursor_fields):
          "cursor_value": <last synced cursor value, or null before the
                            first successful sync>

          # Full-refresh tables (everything else):
          "truncated": <bool -- has truncate() been called for the CURRENT
                         reload cycle? Prevents re-truncating on resume.>,
          "resume_after_pk": <last primary-key value synced this cycle, or
                              null. Only used when the table has exactly one
                              primary-key column, so a resume can skip
                              straight to `WHERE pk > ?` instead of
                              rescanning from the start. Reset to null (and
                              "truncated" to false) once the table finishes,
                              so the *next* full-refresh cycle truncates and
                              reloads again from scratch.>
        }
      }
    }

Design choices, and why:

- Incremental tables use `WHERE cursor_field >= ?` (not `>`), and advance
  the checkpoint after every batch, not just at table completion. That
  makes an interrupted sync resume mid-table from close to where it left
  off. `>=` can re-emit the last row(s) of the previous batch when several
  rows share the exact same cursor value -- that is deliberate and safe,
  because `Operations.upsert()` is a keyed upsert: re-emitting an
  already-synced row is a no-op in the destination, never a duplicate.
- Full-refresh tables with a single-column primary key get the same
  mid-table resumability via keyset pagination (`WHERE pk > ?`).
- Full-refresh tables with no primary key, or a composite one, cannot be
  resumed mid-table (there is no cheap, safe "continue from here" anchor
  without one), so an interruption restarts that table's scan from the
  beginning on the next sync. This is still *correct* -- `truncate()` is
  called at most once per reload cycle, and the table is fully reloaded
  before the cycle is considered done -- just not incremental about it.
  This is a deliberate, documented trade-off, not an oversight.
- Deletes are not detected for incremental tables: a cursor column can only
  tell us about rows that changed, not rows that were removed. Hard
  deletes require either a full-refresh cadence (which does detect them,
  via `truncate()` + full reload) or a source-side tombstone/soft-delete
  column, which this connector does not assume the existence of. See
  README.md.
"""

from typing import Any, Callable, Iterable, Optional

from iris_connector.catalog import TableColumns, discover_schema
from iris_connector.config import IRISConfig
from iris_connector.db import DBConnection
from iris_connector.type_mapping import coerce_value_for_upsert


class SyncOperations:
    """The subset of `fivetran_connector_sdk.Operations` sync needs.

    Declared so tests can pass a plain recorder object instead of the real
    `Operations` class (which requires the SDK's internal operation stream).
    """

    def upsert(self, table: str, data: dict) -> None: ...

    def truncate(self, table: str) -> None: ...

    def checkpoint(self, state: dict) -> None: ...


def _json_safe(value: Any) -> Any:
    """Coerces one cursor/primary-key value into a JSON-serializable form
    for state, preserving int/float/str/bool/None as-is (so comparisons and
    re-binding on the next query stay in the source type) and stringifying
    anything else (datetime, Decimal, etc).
    """
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _build_upsert_data(table: TableColumns, row: tuple) -> dict:
    """Zips one fetched row into an upsert-ready dict, applying
    `coerce_value_for_upsert` per column so values reach
    `Operations.upsert()` in the shape it actually requires (see that
    function's docstring for what was discovered running `fivetran debug`
    for real and why).
    """
    return {
        name: coerce_value_for_upsert(table.fivetran_types[name], value)
        for name, value in zip(table.column_names, row)
    }


def _select_sql(db_schema: str, table: TableColumns, where_clause: str = "", order_by: str = "") -> str:
    columns_sql = ", ".join(table.column_names)
    sql = f"SELECT {columns_sql} FROM {db_schema}.{table.table_name}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return sql


def sync_table_incremental(
    connection: DBConnection,
    ops: SyncOperations,
    db_schema: str,
    table: TableColumns,
    cursor_field: str,
    state: dict,
    batch_size: int,
    warn: Optional[Callable[[str], None]] = None,
) -> None:
    """Full or incremental (depending on prior state) sync of one table via
    `cursor_field`, checkpointing `state` after every batch.
    """
    if cursor_field not in table.column_names:
        if warn:
            warn(
                f"{table.table_name}: configured cursor_field {cursor_field!r} "
                f"is not a syncable column (dropped by type mapping, or does "
                f"not exist); table skipped this sync."
            )
        return

    tables_state = state.setdefault("tables", {})
    table_state = tables_state.setdefault(table.table_name, {"cursor_value": None})
    cursor_value = table_state.get("cursor_value")

    if cursor_value is None:
        sql = _select_sql(db_schema, table, order_by=cursor_field)
        params: tuple = ()
    else:
        sql = _select_sql(db_schema, table, where_clause=f"{cursor_field} >= ?", order_by=cursor_field)
        params = (cursor_value,)

    cursor_idx = table.column_names.index(cursor_field)

    dbcursor = connection.cursor()
    try:
        dbcursor.execute(sql, params)
        while True:
            rows = dbcursor.fetchmany(batch_size)
            if not rows:
                break
            max_cursor_value = cursor_value
            for row in rows:
                ops.upsert(table=table.table_name, data=_build_upsert_data(table, row))
                max_cursor_value = row[cursor_idx]
            cursor_value = max_cursor_value
            table_state["cursor_value"] = _json_safe(cursor_value)
            ops.checkpoint(state=state)
    finally:
        dbcursor.close()


def sync_table_full_refresh(
    connection: DBConnection,
    ops: SyncOperations,
    db_schema: str,
    table: TableColumns,
    state: dict,
    batch_size: int,
) -> None:
    """Truncate-then-reload sync of one table, resumable via keyset
    pagination on the primary key when there is exactly one, checkpointing
    `state` after every batch.
    """
    tables_state = state.setdefault("tables", {})
    default_state = {"truncated": False, "resume_after_pk": None}
    table_state = tables_state.setdefault(table.table_name, dict(default_state))

    resumable_pk = table.primary_key[0] if len(table.primary_key) == 1 else None

    if not table_state.get("truncated"):
        ops.truncate(table=table.table_name)
        table_state["truncated"] = True
        table_state["resume_after_pk"] = None
        # Checkpoint immediately: if the sync is interrupted right after
        # this line, the resume must see truncated=True and never
        # truncate() a second time (which would discard rows this resumed
        # run has already re-upserted).
        ops.checkpoint(state=state)

    resume_after_pk = table_state.get("resume_after_pk")

    if resumable_pk is not None:
        if resume_after_pk is None:
            sql = _select_sql(db_schema, table, order_by=resumable_pk)
            params: tuple = ()
        else:
            sql = _select_sql(
                db_schema, table, where_clause=f"{resumable_pk} > ?", order_by=resumable_pk
            )
            params = (resume_after_pk,)
        pk_idx = table.column_names.index(resumable_pk)
    else:
        sql = _select_sql(db_schema, table)
        params = ()
        pk_idx = None

    dbcursor = connection.cursor()
    try:
        dbcursor.execute(sql, params)
        while True:
            rows = dbcursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                ops.upsert(table=table.table_name, data=_build_upsert_data(table, row))
            if pk_idx is not None:
                table_state["resume_after_pk"] = _json_safe(rows[-1][pk_idx])
            ops.checkpoint(state=state)
    finally:
        dbcursor.close()

    # Table finished: reset to the "fresh" shape so the *next* full-refresh
    # cycle truncates and reloads from scratch again.
    tables_state[table.table_name] = dict(default_state)
    ops.checkpoint(state=state)


def run_sync(
    connection: DBConnection,
    config: IRISConfig,
    state: dict,
    ops: SyncOperations,
    warn: Optional[Callable[[str], None]] = None,
) -> None:
    """Discovers the schema and syncs every table: incrementally if it is
    named in `config.cursor_fields`, full-refresh otherwise.
    """
    tables = discover_schema(
        connection, config.schema, table_allowlist=config.table_allowlist, warn=warn
    )
    cursor_fields = config.cursor_fields or {}

    for table in tables:
        cursor_field = cursor_fields.get(table.table_name)
        if cursor_field:
            sync_table_incremental(
                connection, ops, config.schema, table, cursor_field, state, config.batch_size, warn=warn
            )
        else:
            sync_table_full_refresh(
                connection, ops, config.schema, table, state, config.batch_size
            )

"""The MCP server itself: wires the catalog/query/vector-search tools onto
``mcp.server.mcpserver.MCPServer`` over a ``QueryExecutor``.

Deliberately thin: every tool function here does argument validation +
calls into ``catalog``/``vector``/``db`` and formats the result. All the
actual logic (read-only enforcement, identifier validation, row cap, query
timeout) lives in those modules and is unit-tested there without needing
this MCP-specific layer at all. This module is exercised by
``tests/test_server.py`` through ``call_tool`` against a fake connection,
so the wiring itself -- tool names, argument shapes, read-only annotations
-- is also covered without a live IRIS instance.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import catalog, vector
from .db import DEFAULT_ROW_CAP, DEFAULT_TIMEOUT_SECONDS, QueryExecutor, QueryResult
from .identifiers import InvalidIdentifierError
from .sql_guard import SQLGuardError

__all__ = ["build_server"]

_F = TypeVar("_F", bound=Callable[..., dict[str, Any]])

# Exceptions this module's own validation raises on bad input: the read-only
# guard, identifier validation, and vector.py's own ValueErrors (bad
# top_k/empty vector/etc). These are *expected* rejections of untrusted
# tool-call arguments, not server bugs -- the MCP SDK's default is to treat
# any exception escaping a tool body as a crash (`UnexpectedToolError`,
# logged, not shown to the model as a normal tool result). Wrapping them as
# `ToolError` instead is what makes a rejected `DROP TABLE ...` come back to
# the calling model as an ordinary "tool call failed: <reason>" result, which
# is what an agent needs to see in order to correct itself, rather than as an
# opaque server-side crash.
_EXPECTED_REJECTIONS = (SQLGuardError, InvalidIdentifierError, ValueError)


def _reject_as_tool_error(fn: _F) -> _F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except _EXPECTED_REJECTIONS as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # IRIS DB-API may hand back driver-specific types (Decimal, datetime,
    # bytes, ...) that aren't JSON-serializable as-is; degrade to a string
    # rather than let the whole tool call fail on formatting.
    return str(value)


def _serialize_result(result: QueryResult) -> dict[str, Any]:
    return {
        "columns": result.columns,
        "rows": [[_serialize_value(v) for v in row] for row in result.rows],
        "row_count": result.row_count,
        "truncated": result.truncated,
    }


def build_server(
    executor: QueryExecutor,
    *,
    name: str = "iris-mcp",
    title: str = "InterSystems IRIS (reference)",
) -> MCPServer:
    """Build an ``MCPServer`` with the IRIS tools registered against
    ``executor``. Kept as a plain function (rather than a global module-level
    server instance) so tests can point it at a fake connection and the
    real ``__main__`` entrypoint can point it at a live IRIS namespace,
    without either one importing the other's setup.
    """
    server = MCPServer(
        name=name,
        title=title,
        version="0.1.0",
        instructions=(
            "Tools for exploring and querying an InterSystems IRIS "
            "namespace. list_schemas/list_tables/describe_table explore "
            "structure. run_query executes read-only SQL only: INSERT, "
            "UPDATE, DELETE, DROP, ALTER, TRUNCATE, CALL, GRANT, and "
            "multi-statement payloads are rejected before they ever reach "
            "IRIS. Results are capped at a fixed row count and a query "
            "timeout; truncated=true in a result means more rows existed "
            "than were returned."
        ),
    )

    @server.tool(
        name="list_schemas",
        title="List schemas",
        description="List every SQL schema visible in the connected IRIS namespace.",
        annotations=_READ_ONLY,
    )
    @_reject_as_tool_error
    def list_schemas() -> dict[str, Any]:
        sql, params = catalog.list_schemas_sql()
        result = executor.run_query(sql, params or None)
        return _serialize_result(result)

    @server.tool(
        name="list_tables",
        title="List tables",
        description=(
            "List tables (and views) in the connected IRIS namespace, "
            "optionally filtered to one schema."
        ),
        annotations=_READ_ONLY,
    )
    @_reject_as_tool_error
    def list_tables(schema: str | None = None) -> dict[str, Any]:
        sql, params = catalog.list_tables_sql(schema)
        result = executor.run_query(sql, params or None)
        return _serialize_result(result)

    @server.tool(
        name="describe_table",
        title="Describe table",
        description="List columns, types, and nullability for one table.",
        annotations=_READ_ONLY,
    )
    @_reject_as_tool_error
    def describe_table(schema: str, table: str) -> dict[str, Any]:
        sql, params = catalog.describe_table_sql(schema, table)
        result = executor.run_query(sql, params)
        return _serialize_result(result)

    @server.tool(
        name="run_query",
        title="Run read-only SQL query",
        description=(
            "Execute a single read-only SQL statement (SELECT, or WITH ... "
            "SELECT) against the connected IRIS namespace. Data-modifying "
            "statements and multi-statement payloads are rejected before "
            "execution. Results are capped at a fixed number of rows "
            f"(default {DEFAULT_ROW_CAP}) and a fixed timeout (default "
            f"{DEFAULT_TIMEOUT_SECONDS}s); check the 'truncated' field in "
            "the response."
        ),
        annotations=_READ_ONLY,
    )
    @_reject_as_tool_error
    def run_query(sql: str, row_cap: int | None = None) -> dict[str, Any]:
        result = executor.run_query(sql, row_cap=row_cap)
        return _serialize_result(result)

    @server.tool(
        name="vector_search",
        title="Vector similarity search",
        description=(
            "Find the top-K most similar rows in a table by cosine "
            "similarity between a VECTOR column and a query vector, using "
            "IRIS's native VECTOR_COSINE/TO_VECTOR SQL functions. Read-only."
        ),
        annotations=_READ_ONLY,
    )
    @_reject_as_tool_error
    def vector_search(
        table: str,
        vector_column: str,
        query_vector: list[float],
        select_columns: list[str] | None = None,
        top_k: int = 10,
    ) -> dict[str, Any]:
        sql, params = vector.vector_search_sql(
            table,
            vector_column,
            query_vector,
            select_columns=select_columns,
            top_k=top_k,
        )
        result = executor.run_query(sql, params)
        return _serialize_result(result)

    return server

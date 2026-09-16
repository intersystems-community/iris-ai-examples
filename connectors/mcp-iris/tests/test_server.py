"""End-to-end tests of the MCP tool wiring itself: tool names, argument
shapes, read-only annotations, and that a rejected write statement surfaces
as a tool error rather than an uncaught exception -- all against the fake
DB-API connection, no live IRIS involved.
"""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_iris.db import QueryExecutor
from mcp_iris.server import build_server

from .conftest import FakeConnection, register

# Note on what "tool error" means at this layer: `MCPServer.call_tool()` (the
# direct Python API used below) *raises* `ToolError` for a deliberately
# rejected call -- confirmed by reading mcp.server.mcpserver.tools.base and
# mcp.server.mcpserver.server in the installed `mcp` 2.2.0 package. Over the
# wire (stdio JSON-RPC), the SDK's own request handler
# (`mcp.server.mcpserver.server`, around the `_handle_call_tool`-style
# dispatch) catches exactly this exception type and converts it to
# `CallToolResult(is_error=True, ...)` for the client -- so a rejected
# `DROP TABLE ...` really does reach Claude/ChatGPT as a normal tool error,
# not a crashed connection. That conversion path itself isn't re-exercised
# here since it's the SDK's own tested code, not ours.


@pytest.fixture
def server(fake_connection: FakeConnection):
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=5)
    return build_server(executor)


@pytest.mark.anyio
async def test_lists_expected_tools(server) -> None:
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "list_schemas",
        "list_tables",
        "describe_table",
        "run_query",
        "vector_search",
    }


@pytest.mark.anyio
async def test_every_tool_is_annotated_read_only(server) -> None:
    tools = await server.list_tools()
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name


@pytest.mark.anyio
async def test_list_schemas_returns_structured_result(
    server, fake_connection: FakeConnection
) -> None:
    register(
        fake_connection,
        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME",
        [("SCHEMA_NAME",)],
        [("Sample",), ("User",)],
    )

    result = await server.call_tool("list_schemas", {})

    assert result.is_error is False
    assert result.structured_content["columns"] == ["SCHEMA_NAME"]
    assert result.structured_content["rows"] == [["Sample"], ["User"]]


@pytest.mark.anyio
async def test_describe_table_binds_schema_and_table(
    server, fake_connection: FakeConnection
) -> None:
    register(
        fake_connection,
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
        "ORDINAL_POSITION FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? "
        "AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
        [("COLUMN_NAME",), ("DATA_TYPE",)],
        [("Id", "INTEGER"), ("Name", "VARCHAR")],
    )

    result = await server.call_tool(
        "describe_table", {"schema": "Sample", "table": "Person"}
    )

    assert result.is_error is False
    assert result.structured_content["rows"] == [["Id", "INTEGER"], ["Name", "VARCHAR"]]


@pytest.mark.anyio
async def test_run_query_rejects_write_statement_as_tool_error(server) -> None:
    with pytest.raises(ToolError, match="only SELECT and WITH"):
        await server.call_tool("run_query", {"sql": "DROP TABLE Sample.Person"})


@pytest.mark.anyio
async def test_run_query_rejects_multi_statement_as_tool_error(server) -> None:
    with pytest.raises(ToolError, match="multi-statement"):
        await server.call_tool(
            "run_query",
            {"sql": "SELECT * FROM Sample.Person; DROP TABLE Sample.Person"},
        )


@pytest.mark.anyio
async def test_run_query_executes_select(
    server, fake_connection: FakeConnection
) -> None:
    register(
        fake_connection,
        "SELECT Id FROM Sample.Person",
        [("Id",)],
        [(1,), (2,)],
    )

    result = await server.call_tool("run_query", {"sql": "SELECT Id FROM Sample.Person"})

    assert result.is_error is False
    assert result.structured_content["rows"] == [[1], [2]]


@pytest.mark.anyio
async def test_vector_search_rejects_bad_identifier_as_tool_error(server) -> None:
    with pytest.raises(ToolError, match="invalid identifier"):
        await server.call_tool(
            "vector_search",
            {
                "table": "Ticket; DROP TABLE Foo",
                "vector_column": "SummaryVec",
                "query_vector": [0.1, 0.2],
            },
        )


@pytest.mark.anyio
async def test_vector_search_executes(server, fake_connection: FakeConnection) -> None:
    register(
        fake_connection,
        "SELECT TOP 10 TicketId, VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE)) AS "
        "SIMILARITY FROM KG.Ticket WHERE SummaryVec IS NOT NULL ORDER BY "
        "SIMILARITY DESC",
        [("TicketId",), ("SIMILARITY",)],
        [(101, 0.98)],
    )

    result = await server.call_tool(
        "vector_search",
        {
            "table": "KG.Ticket",
            "vector_column": "SummaryVec",
            "query_vector": [0.1, 0.2],
            "select_columns": ["TicketId"],
            "top_k": 10,
        },
    )

    assert result.is_error is False
    assert result.structured_content["rows"] == [[101, 0.98]]

"""Tests for QueryExecutor: read-only enforcement, row cap, and timeout,
all driven against the fake DB-API connection in conftest.py (no IRIS, no
Docker).
"""

from __future__ import annotations

import time

import pytest

from mcp_iris.db import QueryExecutor, QueryTimeoutError
from mcp_iris.sql_guard import SQLGuardError

from .conftest import FakeConnection, register


def test_run_query_returns_columns_and_rows(fake_connection: FakeConnection) -> None:
    register(
        fake_connection,
        "SELECT Id, Name FROM Sample.Person",
        [("Id",), ("Name",)],
        [(1, "Ada"), (2, "Grace")],
    )
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=5)

    result = executor.run_query("SELECT Id, Name FROM Sample.Person")

    assert result.columns == ["Id", "Name"]
    assert result.rows == [(1, "Ada"), (2, "Grace")]
    assert result.row_count == 2
    assert result.truncated is False


def test_run_query_rejects_write_statements(fake_connection: FakeConnection) -> None:
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=5)

    with pytest.raises(SQLGuardError):
        executor.run_query("DELETE FROM Sample.Person")

    # The guard must run before a connection/cursor is ever touched.
    assert fake_connection.cursors == []


def test_run_query_enforces_row_cap(fake_connection: FakeConnection) -> None:
    rows = [(i,) for i in range(25)]
    register(fake_connection, "SELECT Id FROM Sample.Person", [("Id",)], rows)
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=5)

    result = executor.run_query("SELECT Id FROM Sample.Person")

    assert result.row_count == 10
    assert result.truncated is True
    assert result.rows == rows[:10]


def test_run_query_row_cap_not_truncated_when_result_fits(
    fake_connection: FakeConnection,
) -> None:
    rows = [(i,) for i in range(5)]
    register(fake_connection, "SELECT Id FROM Sample.Person", [("Id",)], rows)
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=5)

    result = executor.run_query("SELECT Id FROM Sample.Person")

    assert result.row_count == 5
    assert result.truncated is False


def test_run_query_per_call_row_cap_overrides_default(
    fake_connection: FakeConnection,
) -> None:
    rows = [(i,) for i in range(5)]
    register(fake_connection, "SELECT Id FROM Sample.Person", [("Id",)], rows)
    executor = QueryExecutor(lambda: fake_connection, row_cap=1000, timeout_seconds=5)

    result = executor.run_query("SELECT Id FROM Sample.Person", row_cap=2)

    assert result.row_count == 2
    assert result.truncated is True


def test_run_query_times_out_on_slow_query(fake_connection: FakeConnection) -> None:
    sql = "SELECT Id FROM Sample.SlowTable"
    register(fake_connection, sql, [("Id",)], [(1,)])
    fake_connection.slow_queries.add(sql.strip().upper())
    fake_connection.sleep_seconds = 2.0
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=0.1)

    start = time.monotonic()
    with pytest.raises(QueryTimeoutError):
        executor.run_query(sql)
    elapsed = time.monotonic() - start

    # The whole point of the timeout is that this call must return close to
    # timeout_seconds, not after the full 2-second sleep.
    assert elapsed < 1.0


def test_run_query_closes_connection_even_on_timeout(
    fake_connection: FakeConnection,
) -> None:
    sql = "SELECT Id FROM Sample.SlowTable"
    register(fake_connection, sql, [("Id",)], [(1,)])
    fake_connection.slow_queries.add(sql.strip().upper())
    fake_connection.sleep_seconds = 2.0
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=0.1)

    with pytest.raises(QueryTimeoutError):
        executor.run_query(sql)

    assert fake_connection.closed is True


def test_run_query_closes_connection_on_success(fake_connection: FakeConnection) -> None:
    register(fake_connection, "SELECT 1", [("1",)], [(1,)])
    executor = QueryExecutor(lambda: fake_connection, row_cap=10, timeout_seconds=5)

    executor.run_query("SELECT 1")

    assert fake_connection.closed is True


def test_run_query_closes_connection_on_guard_rejection_never_opens_one() -> None:
    calls: list[str] = []

    def factory() -> FakeConnection:
        calls.append("opened")
        return FakeConnection()

    executor = QueryExecutor(factory, row_cap=10, timeout_seconds=5)

    with pytest.raises(SQLGuardError):
        executor.run_query("DROP TABLE Sample.Person")

    assert calls == []


def test_invalid_row_cap_rejected() -> None:
    with pytest.raises(ValueError):
        QueryExecutor(lambda: FakeConnection(), row_cap=0)


def test_invalid_timeout_rejected() -> None:
    with pytest.raises(ValueError):
        QueryExecutor(lambda: FakeConnection(), timeout_seconds=0)

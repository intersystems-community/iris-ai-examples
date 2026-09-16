"""Shared fixtures: a fake DB-API connection so tools are testable without
a running IRIS instance (per CLAUDE.md's test-first policy and the
careconnect-sdoh/evals model: offline, no Docker, no API key).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import pytest


@dataclass
class FakeCursor:
    """A minimal PEP-249-shaped cursor good enough to drive the tools.

    ``rows_by_query`` maps a normalized (stripped, upper-cased) SQL string
    to the ``(description, rows)`` pair it should return. Anything not in
    the map returns an empty result set rather than raising, so tests only
    have to register the queries they actually care about.
    """

    rows_by_query: dict[str, tuple[list[tuple[str, ...]], list[tuple[Any, ...]]]]
    slow_queries: set[str] = field(default_factory=set)
    sleep_seconds: float = 0.0
    executed: list[str] = field(default_factory=list)

    description: list[tuple[str, ...]] | None = None
    _rows: list[tuple[Any, ...]] = field(default_factory=list)
    _pos: int = 0
    closed: bool = False

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self.executed.append(sql)
        key = " ".join(sql.strip().upper().split())
        if key in self.slow_queries:
            time.sleep(self.sleep_seconds)
        description, rows = self.rows_by_query.get(key, ([], []))
        self.description = description or None
        self._rows = list(rows)
        self._pos = 0

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        chunk = self._rows[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def fetchall(self) -> list[tuple[Any, ...]]:
        chunk = self._rows[self._pos :]
        self._pos = len(self._rows)
        return chunk

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass
class FakeConnection:
    """A minimal PEP-249-shaped connection wrapping a single FakeCursor."""

    rows_by_query: dict[str, tuple[list[tuple[str, ...]], list[tuple[Any, ...]]]] = field(
        default_factory=dict
    )
    slow_queries: set[str] = field(default_factory=set)
    sleep_seconds: float = 0.0
    closed: bool = False
    committed: bool = False
    rolled_back: bool = False
    cursors: list[FakeCursor] = field(default_factory=list)

    def cursor(self) -> FakeCursor:
        c = FakeCursor(
            rows_by_query=self.rows_by_query,
            slow_queries=self.slow_queries,
            sleep_seconds=self.sleep_seconds,
        )
        self.cursors.append(c)
        return c

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def register(
    conn: FakeConnection,
    sql: str,
    description: list[tuple[str, ...]],
    rows: list[tuple[Any, ...]],
) -> None:
    key = " ".join(sql.strip().upper().split())
    conn.rows_by_query[key] = (description, rows)


@pytest.fixture
def fake_connection() -> FakeConnection:
    return FakeConnection()

"""Connection abstraction and safe query execution.

Everything the MCP tools need from a database connection is expressed as a
``Protocol`` (``DBConnection`` / ``DBCursor``), so tests can hand
``QueryExecutor`` a fake, in-memory connection instead of a live IRIS
instance. The only code in this file that touches the real
``intersystems-irispython`` package is ``IRISConnectionFactory``, and it is
never imported by anything that also imports the fakes used in tests -- the
production adapter and the test double both just satisfy the same Protocol.

``QueryExecutor.run_query`` is where read-only enforcement, the row cap, and
the query timeout are actually applied, in that order:

1. ``sql_guard.assert_read_only`` (unless explicitly disabled, which the MCP
   server never does for the free-text ``run_query`` tool).
2. A wall-clock timeout around ``cursor.execute`` using a worker thread,
   because PEP 249 has no standard way to cancel a running query and IRIS's
   DB-API driver does not expose one either.
3. ``cursor.fetchmany(row_cap + 1)`` instead of ``fetchall()``, so a result
   set larger than the cap never gets fully materialized in this process;
   the ``+1`` is discarded and only used to set ``truncated=True``.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
from typing import Any, Callable, Protocol, Sequence

from .sql_guard import assert_read_only

__all__ = [
    "DBConnection",
    "DBCursor",
    "ConnectionFactory",
    "QueryResult",
    "QueryTimeoutError",
    "QueryExecutor",
    "IRISConnectionConfig",
    "IRISConnectionFactory",
]

DEFAULT_ROW_CAP = 1000
DEFAULT_TIMEOUT_SECONDS = 30.0


class DBCursor(Protocol):
    """The subset of PEP 249 cursor behavior the tools rely on."""

    description: Any

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None: ...

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...


class DBConnection(Protocol):
    """The subset of PEP 249 connection behavior the tools rely on."""

    def cursor(self) -> DBCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


# A zero-argument callable that returns a fresh, ready-to-use connection.
# Using a factory (rather than a single shared connection) keeps each tool
# call isolated and makes the timeout path safe to abandon: if a query
# times out we close that connection and let the next call open a new one,
# instead of reusing a connection that might still have a runaway query on
# it server-side.
ConnectionFactory = Callable[[], DBConnection]


@dataclasses.dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    truncated: bool


class QueryTimeoutError(RuntimeError):
    """Raised when a query does not complete within the configured timeout.

    Note on limitation: PEP 249 does not standardize query cancellation, and
    the IRIS Python DB-API does not expose one either. Timing out here stops
    *this process* from waiting and closes its connection, but cannot
    guarantee the query has stopped running inside IRIS itself. This is
    documented in README.md as a known limitation, not silently assumed
    away.
    """


class QueryExecutor:
    """Runs a single read-only query end-to-end with the safety boundary
    (guard -> timeout -> row cap) applied, against any connection factory
    that satisfies ``ConnectionFactory``.
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        row_cap: int = DEFAULT_ROW_CAP,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if row_cap <= 0:
            raise ValueError("row_cap must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._connection_factory = connection_factory
        self._row_cap = row_cap
        self._timeout_seconds = timeout_seconds

    def run_query(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        row_cap: int | None = None,
        timeout_seconds: float | None = None,
        enforce_read_only: bool = True,
    ) -> QueryResult:
        if enforce_read_only:
            assert_read_only(sql)

        cap = row_cap if row_cap is not None else self._row_cap
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout_seconds

        conn = self._connection_factory()
        try:
            cursor = conn.cursor()
            try:
                self._execute_with_timeout(cursor, sql, params, timeout)
                columns = [d[0] for d in (cursor.description or [])]
                rows = cursor.fetchmany(cap + 1)
                truncated = len(rows) > cap
                if truncated:
                    rows = rows[:cap]
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=truncated,
                )
            finally:
                cursor.close()
        finally:
            conn.close()

    @staticmethod
    def _execute_with_timeout(
        cursor: DBCursor,
        sql: str,
        params: Sequence[Any] | None,
        timeout_seconds: float,
    ) -> None:
        # Deliberately NOT a `with ThreadPoolExecutor() as pool:` block:
        # that context manager's __exit__ calls shutdown(wait=True), which
        # blocks until the worker thread finishes regardless of whether
        # future.result() already timed out -- defeating the timeout
        # entirely for a query that hangs. Shutting down with wait=False
        # on the timeout path lets this method actually return on time;
        # the worker thread (and whatever it's blocked on inside the
        # driver) is abandoned, not forcibly killed -- see QueryTimeoutError
        # docstring for why that's a documented limitation, not a bug.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(cursor.execute, sql, params)
        try:
            future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            pool.shutdown(wait=False)
            raise QueryTimeoutError(
                f"query did not complete within {timeout_seconds}s"
            ) from exc
        else:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Real IRIS connection factory (production adapter). Not exercised by the
# offline test suite -- see STATUS.md for what this needs to be verified
# against a live container.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class IRISConnectionConfig:
    hostname: str
    port: int = 1972
    namespace: str = "USER"
    username: str = "_SYSTEM"
    password: str = ""


class IRISConnectionFactory:
    """Builds a real IRIS connection via ``intersystems-irispython``.

    Import of the ``iris`` package is deferred to call time so that
    importing this module (and therefore all the pure-Python tools that
    live alongside it) never requires the IRIS driver to be installed.
    """

    def __init__(self, config: IRISConnectionConfig) -> None:
        self._config = config

    def __call__(self) -> DBConnection:
        import iris  # local import: see class docstring

        return iris.connect(
            hostname=self._config.hostname,
            port=self._config.port,
            namespace=self._config.namespace,
            username=self._config.username,
            password=self._config.password,
        )

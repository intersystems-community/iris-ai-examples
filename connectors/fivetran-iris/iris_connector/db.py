"""The DB access seam.

Every other module in this package talks to IRIS only through the
`DBConnection` / `DBCursor` structural types (`typing.Protocol`) defined
here -- never through `iris.connect(...)` directly. That is what lets the
whole connector (`schema()`, incremental sync, checkpoint/resume, type
mapping) be driven by `iris_connector.fake_db.FakeConnection` in tests and in
the offline `fivetran debug` demo, with zero code paths that only run when a
real driver is present.

`connect()` below is the *only* function in the package that imports the
real `iris` package (`intersystems-irispython`), and it does so lazily, so
importing this module -- or running the test suite -- never requires that
package to be installed.
"""

from typing import Any, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from iris_connector.config import IRISConfig


@runtime_checkable
class DBCursor(Protocol):
    """The subset of PEP 249 (DB-API 2.0) `Cursor` this connector relies on.

    `intersystems-irispython`'s `iris.dbapi.Cursor` (paramstyle "qmark",
    apilevel "2.0") satisfies this. So does `fake_db.FakeCursor`.
    """

    description: Optional[Sequence[Sequence[Any]]]

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None: ...

    def fetchmany(self, size: int) -> List[Tuple[Any, ...]]: ...

    def fetchall(self) -> List[Tuple[Any, ...]]: ...

    def close(self) -> None: ...


@runtime_checkable
class DBConnection(Protocol):
    """The subset of PEP 249 `Connection` this connector relies on."""

    def cursor(self) -> DBCursor: ...

    def close(self) -> None: ...


def connect(config: IRISConfig) -> DBConnection:
    """Opens a real DB-API connection to IRIS via `intersystems-irispython`.

    Uses `iris.connect(hostname, port, namespace, username, password,
    timeout=...)`, per
    https://docs.intersystems.com (Python DB-API / `intersystems-irispython`)
    and the connectivity reference in `../README.md` at the repo root
    (`connectors/README.md`): superserver port 1972 by default, namespace
    e.g. USER.

    Raises:
        RuntimeError: if the `iris` package is not installed. It is not a
            dependency of the test suite or of the `fake_db`-driven
            `fivetran debug` demo -- only of a real sync against a live
            IRIS instance.
    """
    try:
        import iris  # intersystems-irispython; NOT required for tests/fake debug
    except ImportError as exc:
        raise RuntimeError(
            "The 'iris' package (pip install intersystems-irispython) is "
            "required to connect to a real IRIS instance. It is deliberately "
            "not imported anywhere else in this package, and is not needed "
            "to run the test suite or `fivetran debug` against the bundled "
            "fake connection."
        ) from exc

    return iris.connect(
        config.host,
        config.port,
        config.namespace,
        config.username,
        config.password,
        timeout=config.connection_timeout,
    )

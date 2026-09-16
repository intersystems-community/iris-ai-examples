#
# source-iris: DB-API interface boundary.
#
# Everything above this module (source.py, streams.py, iris_client.py) talks only to
# the `DBAPIConnection` / `DBAPICursor` Protocols defined here — never to the `iris`
# package directly. That is what lets every test in unit_tests/ run against a plain
# Python fake instead of a live IRIS instance/Docker container, per CLAUDE.md's
# test-first policy and this repo's "no Docker in CI" constraint.
#
# The real implementation (`connect_real_iris`) is a thin, ~10-line adapter onto
# `intersystems-irispython`'s DB-API module (`iris.dbapi`), confirmed installable and
# importable in this environment (see STATUS.md for the pasted `pip install` output and
# `python -c "import iris.dbapi"` output). It is intentionally not exercised in
# unit_tests/ (there is no live IRIS to connect to), but its shape follows PEP 249 and
# is covered by unit_tests/test_db.py, which drives it against the same fake, proving
# the interface itself needs nothing IRIS-specific beyond `connect_real_iris`.

from __future__ import annotations

from typing import Any, List, Optional, Protocol, Sequence, Tuple, runtime_checkable


@runtime_checkable
class DBAPICursor(Protocol):
    """The subset of PEP 249 (Python DB-API 2.0) cursor behavior this connector needs."""

    #: Sequence of 7-tuples (name, type_code, ...) once a result set is available, per
    #: PEP 249. We only ever read `description[i][0]` (the column name).
    description: Optional[Sequence[Sequence[Any]]]

    def execute(self, operation: str, parameters: Sequence[Any] = ()) -> Any: ...

    def fetchmany(self, size: int) -> List[Tuple[Any, ...]]: ...

    def fetchall(self) -> List[Tuple[Any, ...]]: ...

    def fetchone(self) -> Optional[Tuple[Any, ...]]: ...

    def close(self) -> None: ...


@runtime_checkable
class DBAPIConnection(Protocol):
    """The subset of PEP 249 connection behavior this connector needs."""

    def cursor(self) -> DBAPICursor: ...

    def close(self) -> None: ...


def connect_real_iris(config: dict) -> DBAPIConnection:
    """
    Build a live IRIS DB-API connection from an Airbyte connector config (see spec.yaml).

    Uses `intersystems-irispython`'s `iris.dbapi.connect`, whose keyword arguments
    (hostname, port, namespace, username, password, timeout) are documented at
    https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=BPYDBAPI_refapi
    ("Python DB-API Quick Reference"). This function is only reachable when a real
    `check`/`discover`/`read` runs against a live IRIS host — never from unit_tests/.
    """
    import iris.dbapi as dbapi  # local import: keep `iris` optional for pure unit tests

    return dbapi.connect(
        hostname=config["host"],
        port=int(config.get("port", 1972)),
        namespace=config.get("namespace", "USER"),
        username=config["username"],
        password=config["password"],
        timeout=int(config.get("connection_timeout_seconds", 20)),
    )

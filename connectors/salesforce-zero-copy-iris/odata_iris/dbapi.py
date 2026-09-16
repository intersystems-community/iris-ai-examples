"""The seam between SQL generation and execution.

Everything above this module (schema, metadata_xml, query_translate) is
pure — no I/O, no IRIS dependency, fully testable without a database.
This module defines the minimal PEP 249 (DB-API 2.0)-shaped Protocol
that `service.py` drives, so tests can hand it a fake connection/cursor
and production code can hand it `iris.connect(...)` (the
`intersystems-irispython` driver referenced in ../../README.md) without
either side changing.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence


class Cursor(Protocol):
    def execute(self, sql: str, params: Sequence[Any] = ()) -> object: ...

    def fetchall(self) -> list[Sequence[Any]]: ...

    @property
    def description(self) -> Sequence[Sequence[Any]] | None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

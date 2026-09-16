"""Test-only helper: replays a table's landing-zone Parquet files in
sequence order and folds them into the row-set Fabric's mirroring engine
would produce, per the documented __rowMarker__ semantics. This lets tests
assert on the *end state* a real Fabric mirrored table would reach, not
just on the raw files this connector wrote.

This is a reimplementation of the documented apply-semantics for test
purposes only; it is not a claim about Fabric's actual server-side
implementation, which this session cannot execute.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

SEQUENCE_RE = re.compile(r"^(\d{20})\.parquet$")

INSERT, UPDATE, DELETE, UPSERT = 0, 1, 2, 4


def replay_table(table_dir: Path, key_columns: list[str]) -> dict[tuple, dict[str, Any]]:
    files = sorted(
        (p for p in table_dir.iterdir() if SEQUENCE_RE.match(p.name)),
        key=lambda p: int(SEQUENCE_RE.match(p.name).group(1)),
    )
    state: dict[tuple, dict[str, Any]] = {}
    for f in files:
        rows = pq.read_table(f).to_pylist()
        for row in rows:
            marker = row.get("__rowMarker__", INSERT)
            key = tuple(row[k] for k in key_columns)
            if marker in (INSERT, UPDATE, UPSERT):
                clean = {k: v for k, v in row.items() if k != "__rowMarker__"}
                state[key] = clean
            elif marker == DELETE:
                state.pop(key, None)
            else:
                raise ValueError(f"Unknown row marker {marker}")
    return state


def sequence_numbers(table_dir: Path) -> list[int]:
    return sorted(
        int(SEQUENCE_RE.match(p.name).group(1))
        for p in table_dir.iterdir()
        if SEQUENCE_RE.match(p.name)
    )

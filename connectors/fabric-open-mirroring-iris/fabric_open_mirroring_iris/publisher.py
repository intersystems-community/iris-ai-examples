"""Orchestrates: IRIS table -> Open Mirroring landing zone.

Design decisions worth calling out (see README.md "Design decisions" for
the full rationale):

1. Initial snapshot batches are written as plain inserts (no
   `__rowMarker__`), matching Microsoft's documented recommendation.
   Snapshot progress is resumable via a row-offset checkpoint, but a
   crash between "batch written" and "checkpoint saved" WILL cause that
   batch's rows to be re-sent as a *new* sequence file on the next run.
   Because Fabric's own Insert semantics for a row that already exists
   is "insert row (no dup validation)" (per spec), a resumed snapshot can
   in principle create duplicate rows in the mirrored table if the source
   table already contained that row. This is called out explicitly in
   STATUS.md as a known limitation with a documented mitigation: run
   `publish_initial_snapshot` only against a target that starts empty, or
   set `idempotent_snapshot=True` (default) which uses Upsert (4) instead
   of plain Insert for snapshot rows too -- upsert-on-retry is a no-op for
   identical data, at the cost of the small extra validation overhead
   Microsoft's docs say plain insert avoids.
2. Incremental changes always use Upsert (4) for source inserts/updates
   and Delete (2) for source deletes -- never plain Insert (0) -- for the
   same idempotency reason: an at-least-once re-send of an incremental
   batch (possible after a crash between file-write and checkpoint-save)
   must never duplicate a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pyarrow as pa

from .iris_types import DELETE, INSERT, UPSERT, iris_schema_to_arrow
from .landing_zone import (
    OpenMirroringLandingZoneWriter,
    WrittenFile,
    build_arrow_table,
    relax_nullability_for_incremental,
    with_row_marker_field,
)
from .source import ChangeRecord, IrisSource
from .state import PublisherState

DEFAULT_SNAPSHOT_BATCH_SIZE = 50_000


@dataclass(frozen=True)
class TableConfig:
    table_name: str
    key_columns: list[str]
    schema: Optional[str] = None
    idempotent_snapshot: bool = True


class FabricOpenMirroringPublisher:
    def __init__(
        self,
        source: IrisSource,
        writer: OpenMirroringLandingZoneWriter,
        state: PublisherState,
    ):
        self.source = source
        self.writer = writer
        self.state = state
        self._arrow_schema_cache: dict[str, pa.Schema] = {}

    def _arrow_schema(self, table_name: str) -> pa.Schema:
        if table_name not in self._arrow_schema_cache:
            cols = self.source.get_table_schema(table_name)
            self._arrow_schema_cache[table_name] = iris_schema_to_arrow(cols)
        return self._arrow_schema_cache[table_name]

    # -- initial snapshot ---------------------------------------------------------
    def publish_initial_snapshot(
        self,
        cfg: TableConfig,
        *,
        batch_size: int = DEFAULT_SNAPSHOT_BATCH_SIZE,
        force: bool = False,
    ) -> list[WrittenFile]:
        table_state = self.state.get(cfg.table_name)
        if table_state.snapshot_done and not force:
            return []
        if force:
            table_state.snapshot_offset = 0
            table_state.snapshot_done = False

        self.writer.ensure_table_metadata(
            cfg.table_name, cfg.key_columns, schema=cfg.schema
        )
        data_schema = self._arrow_schema(cfg.table_name)
        relaxed_schema = relax_nullability_for_incremental(data_schema, cfg.key_columns)
        marker_schema = with_row_marker_field(relaxed_schema) if cfg.idempotent_snapshot else data_schema

        written: list[WrittenFile] = []
        offset = table_state.snapshot_offset
        while True:
            rows = list(
                self.source.fetch_snapshot(cfg.table_name, offset=offset, limit=batch_size)
            )
            if not rows:
                break
            if cfg.idempotent_snapshot:
                for row in rows:
                    row[marker_schema[-1].name] = UPSERT
                table = build_arrow_table(marker_schema, rows)
                wf = self.writer.write_batch(
                    cfg.table_name, table, schema=cfg.schema, is_initial_load=False
                )
            else:
                table = build_arrow_table(data_schema, rows)
                wf = self.writer.write_batch(
                    cfg.table_name, table, schema=cfg.schema, is_initial_load=True
                )
            written.append(wf)
            offset += len(rows)
            table_state.snapshot_offset = offset
            self.state.save()
            if len(rows) < batch_size:
                break

        table_state.snapshot_done = True
        self.state.save()
        return written

    # -- incremental changes --------------------------------------------------------
    def publish_changes(self, cfg: TableConfig) -> Optional[WrittenFile]:
        self.writer.ensure_table_metadata(
            cfg.table_name, cfg.key_columns, schema=cfg.schema
        )
        table_state = self.state.get(cfg.table_name)
        batch = self.source.fetch_changes(cfg.table_name, table_state.change_token)
        if not batch.records:
            return None

        data_schema = self._arrow_schema(cfg.table_name)
        relaxed_schema = relax_nullability_for_incremental(data_schema, cfg.key_columns)
        marker_schema = with_row_marker_field(relaxed_schema)
        rows = _records_to_marker_rows(batch.records, relaxed_schema, cfg.key_columns)

        table = build_arrow_table(marker_schema, rows)
        wf = self.writer.write_batch(
            cfg.table_name, table, schema=cfg.schema, is_initial_load=False
        )
        # State is saved only AFTER the file is durably renamed into place.
        table_state.change_token = batch.next_token
        self.state.save()
        return wf


def _records_to_marker_rows(
    records: list[ChangeRecord],
    data_schema: pa.Schema,
    key_columns: list[str],
) -> list[dict[str, Any]]:
    marker_col = "__rowMarker__"
    rows = []
    for rec in records:
        row = {f.name: rec.row.get(f.name) for f in data_schema}
        if rec.op == "delete":
            row[marker_col] = DELETE
        else:
            # insert and update are both sent as Upsert -- see module
            # docstring, design decision 2.
            row[marker_col] = UPSERT
        rows.append(row)
    return rows

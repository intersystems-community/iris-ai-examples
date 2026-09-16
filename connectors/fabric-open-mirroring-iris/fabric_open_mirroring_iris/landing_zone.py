"""Writer for the Fabric Open Mirroring landing-zone file layout.

Spec source (Microsoft Learn, fetched read-only in this session -- see
README.md "Spec citations" for the exact URLs and STATUS.md for how each
claim below was verified):

  - Folder layout: `<mirrored-db>/Files/LandingZone/<table>/` (or
    `<mirrored-db>/Files/LandingZone/<Schema>.schema/<table>/` with schemas).
  - `_metadata.json` in each table folder declares `keyColumns`; once set,
    keyColumns cannot change.
  - Data files are named with a 20-digit zero-padded sequence number,
    e.g. `00000000000000000001.parquet`, strictly monotonically increasing,
    never reused.
  - `__rowMarker__` is the control column for incremental changes: it must
    be the last column, and its values are 0=Insert, 1=Update, 2=Delete,
    4=Upsert. It is optional (and, per Microsoft's guidance, not
    recommended for performance reasons) on the *initial* load, where an
    absent `__rowMarker__` is treated as Insert.
  - `_partnerEvents.json` is optional-but-recommended, one per mirrored
    database (not per table).

This module writes files to a plain local directory. There is no OneLake
endpoint reachable from this sandbox (and none should be contacted per this
task's hard rules) -- the same directory tree is what a real deployment
would rsync/upload (via the OneLake Blob/ADLS APIs) to
`https://onelake.blob.fabric.microsoft.com/<workspace>/<mirrored-db>/Files/LandingZone/...`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from .iris_types import ROW_MARKER_COLUMN, ROW_MARKER_FIELD

SEQUENCE_FILENAME_RE = re.compile(r"^(\d{20})\.parquet$")
SEQUENCE_DIGITS = 20


class KeyColumnsImmutableError(ValueError):
    pass


@dataclass(frozen=True)
class WrittenFile:
    path: Path
    sequence_number: int


class OpenMirroringLandingZoneWriter:
    """Writes one mirrored database's landing zone under `landing_zone_root`."""

    def __init__(self, landing_zone_root: Path):
        self.landing_zone_root = Path(landing_zone_root)
        self.landing_zone_root.mkdir(parents=True, exist_ok=True)

    # -- paths --------------------------------------------------------------
    def table_dir(self, table_name: str, *, schema: Optional[str] = None) -> Path:
        if schema:
            d = self.landing_zone_root / f"{schema}.schema" / table_name
        else:
            d = self.landing_zone_root / table_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- _metadata.json -------------------------------------------------------
    def ensure_table_metadata(
        self,
        table_name: str,
        key_columns: list[str],
        *,
        schema: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> Path:
        """Create or validate `_metadata.json`. Raises
        `KeyColumnsImmutableError` if an existing file's keyColumns differ
        from the requested ones (per spec, keyColumns cannot be changed
        once set for a table)."""

        path = self.table_dir(table_name, schema=schema) / "_metadata.json"
        payload: dict[str, Any] = {"keyColumns": list(key_columns)}
        if extra:
            payload.update(extra)

        if path.exists():
            existing = json.loads(path.read_text())
            if existing.get("keyColumns") != list(key_columns):
                raise KeyColumnsImmutableError(
                    f"_metadata.json for '{table_name}' already declares "
                    f"keyColumns={existing.get('keyColumns')!r}; cannot change "
                    f"to {list(key_columns)!r} without dropping and recreating "
                    "the table folder (per Open Mirroring spec)."
                )
            return path

        _atomic_write_text(path, json.dumps(payload, indent=2))
        return path

    def write_partner_events(
        self,
        *,
        partner_name: str,
        source_type: str,
        source_version: str,
        additional_information: Optional[dict[str, str]] = None,
    ) -> Path:
        """Write `_partnerEvents.json` at the mirrored-database (landing
        zone root) level.

        PLACEMENT NOTE: Microsoft's docs state this file is "placed at
        mirrored database level, not per table" but the exact directory
        (the `LandingZone/` root used here, vs. one level up at the
        mirrored-database's `Files/` root) was not pinned down to a single
        unambiguous example in the pages this session could fetch. Flagged
        UNVERIFIED in STATUS.md -- confirm against a live Fabric workspace
        or the `open-mirroring-tutorial` walkthrough before relying on it.
        """

        path = self.landing_zone_root / "_partnerEvents.json"
        payload = {
            "partnerName": partner_name,
            "sourceInfo": {
                "sourceType": source_type,
                "sourceVersion": source_version,
                "additionalInformation": additional_information or {},
            },
        }
        _atomic_write_text(path, json.dumps(payload, indent=2))
        return path

    # -- sequencing -----------------------------------------------------------
    def next_sequence_number(self, table_name: str, *, schema: Optional[str] = None) -> int:
        """Authoritative next sequence number, derived by scanning the
        table directory for existing `NNNNNNNNNNNNNNNNNNNN.parquet` files
        and returning max+1 (or 1 if none exist).

        Scanning the directory (rather than trusting only local state) is
        what makes a crashed-and-restarted publisher self-healing: even if
        local bookkeeping is stale or was never written, the next call
        always continues the real on-disk sequence and never reuses or
        skips a number.
        """

        d = self.table_dir(table_name, schema=schema)
        max_seq = 0
        for entry in d.iterdir():
            m = SEQUENCE_FILENAME_RE.match(entry.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        return max_seq + 1

    # -- data files -------------------------------------------------------------
    def write_batch(
        self,
        table_name: str,
        table: pa.Table,
        *,
        schema: Optional[str] = None,
        is_initial_load: bool,
    ) -> WrittenFile:
        """Write one Parquet data file at the next sequence number.

        `table` must already have `__rowMarker__` as its last column when
        `is_initial_load` is False, and must NOT have it when
        `is_initial_load` is True (initial-load rows are always plain
        inserts; see module docstring).
        """

        has_marker = ROW_MARKER_COLUMN in table.column_names
        if is_initial_load and has_marker:
            raise ValueError(
                "Initial-load batches must not include __rowMarker__ "
                "(absent __rowMarker__ is treated as Insert during initial load)."
            )
        if not is_initial_load and not has_marker:
            raise ValueError(
                "Incremental batches must include __rowMarker__ as the last column."
            )
        if has_marker and table.column_names[-1] != ROW_MARKER_COLUMN:
            raise ValueError("__rowMarker__ must be the last column.")

        d = self.table_dir(table_name, schema=schema)
        seq = self.next_sequence_number(table_name, schema=schema)
        final_name = f"{seq:0{SEQUENCE_DIGITS}d}.parquet"
        final_path = d / final_name
        tmp_path = d / f"_{final_name}.tmp"

        pq.write_table(table, tmp_path)
        os.replace(tmp_path, final_path)  # atomic rename on the same filesystem

        return WrittenFile(path=final_path, sequence_number=seq)


def build_arrow_table(schema: pa.Schema, rows: list[dict[str, Any]]) -> pa.Table:
    columns = {field.name: [row.get(field.name) for row in rows] for field in schema}
    arrays = [pa.array(columns[field.name], type=field.type) for field in schema]
    return pa.Table.from_arrays(arrays, schema=schema)


def with_row_marker_field(schema: pa.Schema) -> pa.Schema:
    """Append the `__rowMarker__` control column to a data schema, as the
    required last column, for incremental (non-initial-load) batches."""

    return pa.schema(list(schema) + [ROW_MARKER_FIELD])


def relax_nullability_for_incremental(schema: pa.Schema, key_columns: list[str]) -> pa.Schema:
    """Return `schema` with every non-key column forced nullable=True.

    Rationale: the Open Mirroring spec says an *update* row "must contain
    the full row data, with all columns" but does not equally pin down
    whether a *delete* row must carry non-key column values (see the
    UNVERIFIED note in `landing_zone.py`'s module docstring and
    STATUS.md). This connector fills delete rows' non-key columns with
    NULL rather than guessing stale values, so those columns must be
    nullable in the Arrow/Parquet schema of an incremental file even when
    the source IRIS column is declared NOT NULL. Key columns stay exactly
    as declared (never relaxed) because a delete or update with a NULL key
    would be meaningless.
    """

    fields = []
    for f in schema:
        if f.name in key_columns:
            fields.append(f)
        else:
            fields.append(f.with_nullable(True))
    return pa.schema(fields)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)

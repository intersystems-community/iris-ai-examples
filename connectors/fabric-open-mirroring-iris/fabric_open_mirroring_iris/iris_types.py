"""IRIS SQL -> Apache Arrow / Parquet type mapping.

Fabric Open Mirroring ingests Parquet files whose logical/physical type
combinations must be valid Parquet (see
https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring-landing-zone-format
-> "Parquet file format" section: "The parquet files needs to follow standard
parquet constraints and have a valid combination of logical type and physical
type."). PyArrow's own Parquet writer always emits a valid logical/physical
pairing for the Arrow types below, so we map to Arrow types and let PyArrow
choose the on-disk Parquet representation -- we do not hand-construct Parquet
footers.

Column introspection is done against ``INFORMATION_SCHEMA.COLUMNS`` so this
module depends only on IRIS SQL data type *names* as returned by that view,
not on any particular IRIS Python driver's internal type codes (those are
driver-private and not documented as a stable contract).

VERIFICATION NOTE (see ../STATUS.md): the IRIS SQL data type name list below
is drawn from general InterSystems IRIS SQL documentation knowledge. This
session could not re-verify it against docs.intersystems.com (egress to that
domain is blocked in this sandbox -- see STATUS.md). Treat the exact set of
type name spellings as UNVERIFIED until checked against a live IRIS
INFORMATION_SCHEMA.COLUMNS.DATA_TYPE result or the IRIS SQL Reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pyarrow as pa


@dataclass(frozen=True)
class ColumnDef:
    """One column as introspected from IRIS INFORMATION_SCHEMA.COLUMNS."""

    name: str
    iris_type: str  # DATA_TYPE value, e.g. "VARCHAR", "BIGINT", "NUMERIC"
    nullable: bool = True
    precision: Optional[int] = None  # NUMERIC_PRECISION
    scale: Optional[int] = None  # NUMERIC_SCALE
    max_length: Optional[int] = None  # CHARACTER_MAXIMUM_LENGTH


# IRIS SQL data type name (upper-cased) -> zero-arg Arrow type factory, or a
# factory that additionally consumes the ColumnDef for parameterized types.
_SIMPLE_MAP = {
    "BIGINT": pa.int64(),
    "INTEGER": pa.int32(),
    "INT": pa.int32(),
    "SMALLINT": pa.int16(),
    "TINYINT": pa.int8(),
    "DOUBLE": pa.float64(),
    "FLOAT": pa.float64(),
    "REAL": pa.float32(),
    "CHAR": pa.string(),
    "VARCHAR": pa.string(),
    "LONGVARCHAR": pa.string(),
    "NVARCHAR": pa.string(),
    "DATE": pa.date32(),  # logical DATE / physical INT32 -- valid combo
    "TIME": pa.time64("us"),
    "TIMESTAMP": pa.timestamp("us"),
    "TIMESTAMP2": pa.timestamp("us"),
    "BIT": pa.bool_(),
    "BOOLEAN": pa.bool_(),
    "VARBINARY": pa.binary(),
    "LONGVARBINARY": pa.binary(),
    "BINARY": pa.binary(),
    "IMAGE": pa.binary(),
    "GUID": pa.string(),
    "UNIQUEIDENTIFIER": pa.string(),
    "JSON": pa.string(),
}

# IRIS types this connector deliberately does NOT attempt to map, and why.
# Any column reported with one of these types is excluded from the outgoing
# Arrow schema by `iris_schema_to_arrow` (with a warning), rather than being
# silently coerced.
UNSUPPORTED_IRIS_TYPES = {
    "LIST": (
        "IRIS $LISTBUILD-encoded ('%25List' storage) columns are an "
        "IRIS-internal binary encoding, not a scalar SQL value. Decoding "
        "requires IRIS-side $LISTTOSTRING/$LISTGET conversion in the "
        "extraction SQL (e.g. project the column through a view that calls "
        "$LISTTOSTRING) before this connector can carry it as a string."
    ),
    "OBJECT": (
        "Embedded object / relationship-valued (OREF) columns are not "
        "scalar SQL values and are not projected by a plain SELECT column "
        "list in a form this connector can map 1:1 to a Parquet column."
    ),
}


def iris_column_to_arrow_field(col: ColumnDef) -> pa.Field:
    """Map one IRIS column to a PyArrow field, or raise if unsupported."""

    key = col.iris_type.upper().strip()
    if key in UNSUPPORTED_IRIS_TYPES:
        raise UnsupportedIrisTypeError(col.name, col.iris_type, UNSUPPORTED_IRIS_TYPES[key])

    if key in ("NUMERIC", "DECIMAL"):
        precision = col.precision or 38
        scale = col.scale if col.scale is not None else 10
        # Parquet decimal128 supports precision up to 38.
        precision = min(precision, 38)
        arrow_type = pa.decimal128(precision, scale)
    elif key in _SIMPLE_MAP:
        arrow_type = _SIMPLE_MAP[key]
    else:
        # Unknown-but-not-explicitly-unsupported type: fall back to string
        # rather than silently dropping data. Documented in README as the
        # conservative default for any IRIS SQL type not in the known list.
        arrow_type = pa.string()

    return pa.field(col.name, arrow_type, nullable=col.nullable)


class UnsupportedIrisTypeError(ValueError):
    def __init__(self, column_name: str, iris_type: str, reason: str):
        super().__init__(
            f"Column '{column_name}' has IRIS type '{iris_type}' which this "
            f"connector does not map to Parquet: {reason}"
        )
        self.column_name = column_name
        self.iris_type = iris_type


def iris_schema_to_arrow(columns: list[ColumnDef], *, skip_unsupported: bool = False) -> pa.Schema:
    """Map a full IRIS table schema to an Arrow schema.

    If ``skip_unsupported`` is False (default), an unsupported column type
    raises. If True, unsupported columns are silently omitted -- callers
    that pass True are responsible for logging what was dropped.
    """

    fields = []
    for col in columns:
        try:
            fields.append(iris_column_to_arrow_field(col))
        except UnsupportedIrisTypeError:
            if skip_unsupported:
                continue
            raise
    return pa.schema(fields)


ROW_MARKER_COLUMN = "__rowMarker__"

# Row marker codes per
# https://learn.microsoft.com/en-us/fabric/mirroring/open-mirroring-landing-zone-format
INSERT = 0
UPDATE = 1
DELETE = 2
UPSERT = 4

ROW_MARKER_FIELD = pa.field(ROW_MARKER_COLUMN, pa.int32(), nullable=False)

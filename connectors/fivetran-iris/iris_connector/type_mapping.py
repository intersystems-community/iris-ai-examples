"""IRIS -> Fivetran type mapping.

Source of truth for the IRIS side: `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`
values as exposed through ODBC/JDBC (and therefore through the Python
DB-API driver, `intersystems-irispython`): BIGINT, BIT, DATE, DOUBLE, GUID,
INTEGER, LONGVARBINARY, LONGVARCHAR, NUMERIC, OREF, POSIXTIME, SMALLINT,
TIME, TIMESTAMP, TINYINT, VARBINARY, VARCHAR (plus CHAR/FLOAT variants of
the same families). `LONGVARCHAR`/`LONGVARBINARY` are IRIS's DATA_TYPE
strings for the `%Stream.GlobalCharacter` / `%Stream.GlobalBinary` classes.
`POSIXTIME` is IRIS's `%Library.PosixTime` (an encoded 64-bit int on disk,
formatted by the driver as `YYYY-MM-DD HH:MM:SS.FFFFFF` on the wire).

Source of truth for the Fivetran side: the `DataType` enum actually usable
through `fivetran_connector_sdk` 2.12.1 -- read from the installed
package, not guessed:
  - `connector_helper.process_data_type()` is what `schema()`'s string
    column types go through; it recognizes BOOLEAN, SHORT, INT, LONG,
    DECIMAL, FLOAT, DOUBLE, NAIVE_DATE, NAIVE_DATETIME, UTC_DATETIME,
    BINARY, XML, STRING, JSON.
  - The wire protocol (`common_pb2.DataType`) additionally defines
    `NAIVE_TIME`, but `type_coercion.py` maps it to `_raise_unsupported_type`
    and `process_data_type()` has no case for the string "NAIVE_TIME" /
    "TIME" -- so it is not actually usable in this SDK version. There is no
    native Fivetran time-of-day type we can target.

This module documents, for every mapping, *why* it was chosen and what is
deliberately dropped -- see the module-level `DROPPED_TYPES` docstring and
`README.md`'s type mapping table for the human-readable version.
"""

import re
from typing import Any, Callable, Optional, Union

# DECIMAL precision/scale bounds. Fivetran's `DecimalParams` fields are
# plain protobuf `int32`s with no bound enforced by the SDK itself, but 38
# is the de facto ceiling used across Fivetran's own connectors (matches
# standard SQL NUMERIC(38, ...) / Snowflake's own NUMBER ceiling) and IRIS's
# %Library.Numeric practical precision. We clamp defensively rather than
# forwarding an IRIS-reported precision/scale that would not round-trip.
MAX_DECIMAL_PRECISION = 38

#: IRIS DATA_TYPE values that are dropped from the synced schema entirely
#: (not merely type-mapped). Documented individually below; summarized:
#:   LONGVARCHAR / LONGVARBINARY -- %Stream.* columns. IRIS SQL forbids
#:     using a stream column in most scalar/aggregate functions or in a
#:     WHERE clause (SQLCODE -37), so a stream column can never be a cursor
#:     field, and a naive `SELECT *` can return a stream *object* rather
#:     than inline data depending on driver/fetch mode. Fully supporting
#:     them means a second per-row read-the-stream round trip and a size
#:     policy (inline vs. Fivetran file upload) that has no way to be
#:     verified without a live IRIS instance. Dropped for this iteration;
#:     see README.md and STATUS.md.
#:   OREF -- an in-process object reference / OID, not durable column data;
#:     meaningless outside the originating IRIS process.
DROPPED_TYPES = frozenset({"LONGVARCHAR", "LONGVARBINARY", "OREF"})

# Simple (parameterless) mappings.
_SIMPLE: dict = {
    "BIGINT": "LONG",
    "INTEGER": "INT",
    "INT": "INT",
    "SMALLINT": "SHORT",
    # Fivetran has no 8-bit integer type; SHORT (16-bit) is the smallest
    # available and never truncates a TINYINT's range (0-255 / -128-127).
    "TINYINT": "SHORT",
    "BIT": "BOOLEAN",
    "DOUBLE": "DOUBLE",
    "FLOAT": "DOUBLE",
    "REAL": "FLOAT",
    "VARCHAR": "STRING",
    "CHAR": "STRING",
    "GUID": "STRING",
    "DATE": "NAIVE_DATE",
    # IRIS TIMESTAMP (%Library.TimeStamp) carries no timezone; Fivetran's
    # NAIVE_DATETIME is the corresponding "wall clock, no offset" type.
    "TIMESTAMP": "NAIVE_DATETIME",
    # %Library.PosixTime is defined as seconds-since-epoch (UTC by
    # construction), so it maps to Fivetran's UTC_DATETIME. UNVERIFIED
    # against a live IRIS instance: whether the DB-API driver's ODBC-mode
    # formatting (`YYYY-MM-DD HH:MM:SS.FFFFFF`) is *always* the UTC wall
    # clock rather than a server-local rendering. See STATUS.md.
    "POSIXTIME": "UTC_DATETIME",
    "VARBINARY": "BINARY",
    "BINARY": "BINARY",
    # No native Fivetran time-of-day type is usable in SDK 2.12.1 (see
    # module docstring) -- represent as plain text "HH:MM:SS[.ffffff]".
    "TIME": "STRING",
}


def map_iris_type(
    data_type: str,
    character_maximum_length: Optional[int] = None,
    numeric_precision: Optional[int] = None,
    numeric_scale: Optional[int] = None,
    *,
    warn: Optional[Callable[[str], None]] = None,
    context: str = "",
) -> Optional[Union[str, dict]]:
    """Maps one `INFORMATION_SCHEMA.COLUMNS` row to a Fivetran column type.

    Args:
        data_type: `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`, e.g. "VARCHAR".
            Compared case-insensitively; IRIS returns it upper-case, but we
            do not depend on that.
        character_maximum_length: unused today (Fivetran STRING is
            unbounded); accepted for interface stability and possible
            future `string_byte_length` hinting.
        numeric_precision: `NUMERIC_PRECISION`, required to map NUMERIC.
        numeric_scale: `NUMERIC_SCALE`, required to map NUMERIC.
        warn: optional callable (e.g. `Logging.warning`) invoked with a
            human-readable message whenever a type is dropped, clamped, or
            falls back to STRING.
        context: human-readable "table.column" prefix for warning messages.

    Returns:
        A Fivetran column type: either a plain string (e.g. "STRING"), a
        `{"type": "DECIMAL", "precision": int, "scale": int}` dict (the only
        shape `fivetran_connector_sdk.process_columns` accepts for
        parameterized types), or `None` if the column should be dropped
        from the synced schema (see `DROPPED_TYPES`).
    """

    def _warn(message: str) -> None:
        if warn is not None:
            warn(f"{context}: {message}" if context else message)

    if data_type is None:
        _warn("NULL DATA_TYPE reported by INFORMATION_SCHEMA; column dropped.")
        return None

    dt = data_type.strip().upper()

    if dt in DROPPED_TYPES:
        _warn(
            f"IRIS type {dt} is not synced by this connector "
            f"(see type_mapping.DROPPED_TYPES / README.md); column dropped."
        )
        return None

    if dt in _SIMPLE:
        return _SIMPLE[dt]

    if dt == "NUMERIC":
        return _map_numeric(numeric_precision, numeric_scale, _warn)

    _warn(f"unrecognized IRIS DATA_TYPE {dt!r}; falling back to STRING.")
    return "STRING"


def _map_numeric(
    numeric_precision: Optional[int],
    numeric_scale: Optional[int],
    warn: Callable[[str], None],
) -> dict:
    """Maps NUMERIC(precision, scale) to Fivetran DECIMAL, clamping to
    `MAX_DECIMAL_PRECISION` and coercing missing precision/scale to safe
    defaults rather than guessing at a wider type.
    """
    precision = numeric_precision
    scale = numeric_scale

    if precision is None:
        warn(
            "NUMERIC column has no NUMERIC_PRECISION reported; defaulting to "
            f"DECIMAL({MAX_DECIMAL_PRECISION}, {scale or 0})."
        )
        precision = MAX_DECIMAL_PRECISION
    if scale is None:
        scale = 0

    if precision > MAX_DECIMAL_PRECISION:
        warn(
            f"NUMERIC_PRECISION={precision} exceeds this connector's cap of "
            f"{MAX_DECIMAL_PRECISION}; clamping (values may lose leading digits)."
        )
        precision = MAX_DECIMAL_PRECISION
    if scale > precision:
        warn(
            f"NUMERIC_SCALE={scale} exceeds NUMERIC_PRECISION={precision}; "
            f"clamping scale to precision."
        )
        scale = precision

    return {"type": "DECIMAL", "precision": precision, "scale": scale}


# Discovered by actually running `fivetran debug` against this connector
# (see STATUS.md/README.md): `fivetran_connector_sdk`'s UTC_DATETIME parser
# (`type_coercion._parse_utc_datetime_str`) *requires* a trailing UTC offset
# or "Z" in the string ("...+00:00" / "...Z") and raises ValueError without
# one. IRIS's DB-API driver formats `%Library.PosixTime` in ODBC mode as
# `YYYY-MM-DD HH:MM:SS.FFFFFF` -- no offset at all -- even though the type
# is *defined* as seconds-since-epoch (i.e. an unambiguous UTC instant). So
# a raw driver value can never satisfy the SDK's own parser; this
# connector must append the offset itself before upsert.
_OFFSET_SUFFIX_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def coerce_value_for_upsert(fivetran_type: Union[str, dict], value: Any) -> Any:
    """Adjusts one already-fetched row value into the exact shape
    `fivetran_connector_sdk.Operations.upsert()` requires for its mapped
    Fivetran column type, given what a real `fivetran debug` run against
    this connector actually accepted or rejected. Call this on every value
    before `Operations.upsert()`, not only on values `map_iris_type` had to
    think hard about -- e.g. BOOLEAN also needed a fix.

    NULL passthrough: `None` is returned unchanged for every type; the SDK
    encodes it as SQL NULL regardless of the column's declared type
    (`operations._map_data_to_columns`), so there is nothing to coerce.
    """
    if value is None:
        return value

    if fivetran_type == "UTC_DATETIME" and isinstance(value, str):
        v = value.strip()
        if not _OFFSET_SUFFIX_RE.search(v):
            v = f"{v}+00:00"
        return v

    return value

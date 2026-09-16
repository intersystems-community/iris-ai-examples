#
# source-iris: IRIS SQL -> Airbyte JSON Schema type mapping.
#
# The mapping is derived from InterSystems IRIS SQL Reference, "Data Types (SQL)"
# (https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=RSQL_datatype)
# and from INFORMATION_SCHEMA.COLUMNS.DATA_TYPE, which reports the column's *ODBC* type
# name (e.g. a %Library.PosixTime column reports DATA_TYPE = 'TIMESTAMP', not 'BIGINT',
# because %PosixTime's documented ODBC type is TIMESTAMP). See STATUS.md and README.md
# "Type mapping" section for what is verified vs. assumed, since there is no live IRIS
# instance available to confirm this end-to-end.
#
# This module is intentionally pure (no DB access) so it is fully unit-testable offline.

from __future__ import annotations

from typing import Any, Dict, Optional

# IRIS DATA_TYPE strings (as reported by INFORMATION_SCHEMA.COLUMNS) that we know are
# stream/LOB types. Reading these via SQL through the DB-API is unreliable for large
# objects and they can never be used in a WHERE/ORDER BY clause (SQLCODE -313/-37), so
# a stream column can never be a cursor field or part of the primary key we build
# ourselves. We still surface them as a best-effort string field.
LOB_TYPES = {"LONGVARCHAR", "LONGVARBINARY", "CLOB", "BLOB"}

# Base (non-nullable) JSON Schema fragment per IRIS DATA_TYPE. Anything not found here
# falls back to {"type": "string"} per Airbyte's own documented recommendation for
# connectors that encounter an unknown source type, and is recorded in the returned
# UnmappedType marker so callers/tests can see it happened.
_BASE_TYPE_MAP: Dict[str, Dict[str, Any]] = {
    # Exact integers
    "TINYINT": {"type": "integer"},
    "SMALLINT": {"type": "integer"},
    "INTEGER": {"type": "integer"},
    "INT": {"type": "integer"},
    "BIGINT": {"type": "integer"},
    # BIGINT is a 64-bit signed integer. That is within the range IEEE-754 doubles can
    # represent losslessly (+/-2^53) only up to ~9.007e15; IRIS BIGINT can hold up to
    # ~9.223e18. We flag it as a "big integer" via airbyte_type so destinations that
    # care about exactness (e.g. writing to another BIGINT column) do not round-trip
    # through a JSON double. See NUMERIC handling below for the same concern.
    # (Applied in map_iris_type, not here, because it depends on precision.)
    # Approximate / fixed-point numerics
    "NUMERIC": {"type": "number"},
    "DECIMAL": {"type": "number"},
    "DOUBLE": {"type": "number"},
    "FLOAT": {"type": "number"},
    "REAL": {"type": "number"},
    # Boolean (IRIS %Boolean is stored as BIT/INTEGER 0/1 and reported as BIT by ODBC)
    "BIT": {"type": "boolean"},
    "BOOLEAN": {"type": "boolean"},
    # Character
    "CHAR": {"type": "string"},
    "VARCHAR": {"type": "string"},
    "LONGVARCHAR": {"type": "string"},
    "CLOB": {"type": "string"},
    "GUID": {"type": "string"},
    "UNIQUEIDENTIFIER": {"type": "string"},
    # Binary — emitted as a base64-able opaque string; Airbyte has no native "bytes"
    # JSON Schema type, so downstream connectors that need real bytes must base64
    # decode. We do not do the encoding ourselves in this module (see streams.py).
    "BINARY": {"type": "string"},
    "VARBINARY": {"type": "string"},
    "LONGVARBINARY": {"type": "string"},
    "BLOB": {"type": "string"},
    # Date/Time. IRIS %Date/%Time/%TimeStamp/%PosixTime all report their *ODBC* type
    # here (DATE / TIME / TIMESTAMP), which is what INFORMATION_SCHEMA.COLUMNS exposes.
    # %PosixTime and %TimeStamp are therefore indistinguishable at the catalog level;
    # both are mapped to a date-time string. See the %PosixTime note in README.md.
    "DATE": {"type": "string", "format": "date"},
    "TIME": {"type": "string"},
    "TIMESTAMP": {"type": "string", "format": "date-time", "airbyte_type": "timestamp_without_timezone"},
}


def quote_ident(identifier: str) -> str:
    """
    Safely quote a single SQL identifier (schema, table, or column name) for IRIS SQL.

    IRIS uses the ANSI SQL double-quote delimited-identifier convention: wrap in `"` and
    double any embedded `"`. This is the ONLY function in this connector allowed to build
    a fragment of SQL text out of a name that came from the catalog/config; every query
    string in iris_client.py must route identifiers through this (or quote_qualified)
    rather than interpolating raw strings, so a table or column name can never break out
    of its quoting and inject SQL.
    """
    if identifier is None:
        raise ValueError("SQL identifier must not be None")
    return '"' + identifier.replace('"', '""') + '"'


def quote_qualified(schema: str, table: str) -> str:
    """Safely quote a schema-qualified table reference, e.g. "SQLUser"."MyTable"."""
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def map_iris_type(
    data_type: str,
    *,
    is_nullable: bool = True,
    numeric_precision: Optional[int] = None,
    numeric_scale: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Map one IRIS INFORMATION_SCHEMA.COLUMNS row's DATA_TYPE (+ nullability/precision)
    to an Airbyte JSON Schema fragment for a single field.

    Unknown/unrecognized IRIS types fall back to {"type": "string"} rather than raising,
    because discover() must never fail outright on one odd column — see
    docs/iris.md "Type mapping" and unit_tests/test_type_mapping.py::test_unknown_type_falls_back_to_string.
    """
    key = (data_type or "").strip().upper()
    base = dict(_BASE_TYPE_MAP.get(key, {"type": "string"}))

    # NUMERIC/DECIMAL with scale 0 and precision beyond safe-double range, and BIGINT,
    # are exact integers Airbyte's JSON "integer" type cannot always represent exactly
    # in a JSON-number-based destination. Mark them explicitly so lossless destinations
    # can special-case them; this does not change the JSON Schema "type" itself.
    if key == "BIGINT":
        base["airbyte_type"] = "big_integer"
    elif key in ("NUMERIC", "DECIMAL"):
        if numeric_scale == 0 and (numeric_precision or 0) > 15:
            base["airbyte_type"] = "big_integer"
        elif (numeric_precision or 0) > 15:
            base["airbyte_type"] = "big_number"

    json_type = base.get("type")
    if is_nullable and json_type is not None:
        base = dict(base)
        base["type"] = [json_type, "null"] if not isinstance(json_type, list) else json_type + ["null"]

    return base


def is_lob_type(data_type: str) -> bool:
    """True if this IRIS DATA_TYPE is a stream/LOB type that cannot appear in WHERE/ORDER BY."""
    return (data_type or "").strip().upper() in LOB_TYPES

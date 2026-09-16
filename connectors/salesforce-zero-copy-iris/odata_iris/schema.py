"""Declared table schema: the whitelist everything else in this package
trusts. No SQL identifier reaches the query builder unless it is present
here — that is the core of the injection defense in query_translate.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Minimal IRIS SQL type name -> OData v4 EDM primitive type mapping.
# IRIS type names as reported by ODBC/JDBC metadata / %SQL catalog queries
# (INFORMATION_SCHEMA.COLUMNS.DATA_TYPE). Extend as needed; unknown types
# fall back to Edm.String rather than raising, since $metadata must still
# be produced for a superset of columns a real table may have.
IRIS_TO_EDM_TYPE = {
    "BIGINT": "Edm.Int64",
    "INTEGER": "Edm.Int32",
    "INT": "Edm.Int32",
    "SMALLINT": "Edm.Int16",
    "TINYINT": "Edm.Byte",
    "NUMERIC": "Edm.Decimal",
    "DECIMAL": "Edm.Decimal",
    "DOUBLE": "Edm.Double",
    "FLOAT": "Edm.Double",
    "REAL": "Edm.Single",
    "VARCHAR": "Edm.String",
    "CHAR": "Edm.String",
    "LONGVARCHAR": "Edm.String",
    "DATE": "Edm.Date",
    "TIME": "Edm.TimeOfDay",
    "TIMESTAMP": "Edm.DateTimeOffset",
    "BIT": "Edm.Boolean",
    "BOOLEAN": "Edm.Boolean",
}


@dataclass(frozen=True)
class Column:
    name: str
    iris_type: str
    nullable: bool = True

    @property
    def edm_type(self) -> str:
        return IRIS_TO_EDM_TYPE.get(self.iris_type.upper(), "Edm.String")


@dataclass(frozen=True)
class EntitySet:
    """Maps one OData EntitySet to one IRIS table.

    `name` is the OData entity set / entity type name exposed in
    $metadata and in request URLs. `table` is the real IRIS table
    (schema-qualified, e.g. "SQLUser.Patient") queried under the hood.
    `key` must name a column present in `columns`.
    """

    name: str
    table: str
    columns: tuple[Column, ...]
    key: str

    def __post_init__(self) -> None:
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate column names in entity set {self.name!r}")
        if self.key not in names:
            raise ValueError(
                f"key {self.key!r} is not a declared column of entity set {self.name!r}"
            )

    def column(self, name: str) -> Column | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    @property
    def column_names(self) -> frozenset[str]:
        return frozenset(c.name for c in self.columns)


@dataclass(frozen=True)
class Schema:
    """A named collection of entity sets — the whole surface exposed by
    one $metadata document / one service root."""

    namespace: str
    entity_sets: tuple[EntitySet, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        names = [e.name for e in self.entity_sets]
        if len(names) != len(set(names)):
            raise ValueError("duplicate entity set names in schema")

    def entity_set(self, name: str) -> EntitySet | None:
        for e in self.entity_sets:
            if e.name == name:
                return e
        return None

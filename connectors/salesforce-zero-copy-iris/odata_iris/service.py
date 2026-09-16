"""Wires schema + query_translate + a DB-API connection into OData
request handling. No HTTP framework here on purpose — see README.md for
why this stays a library rather than a running server in this
environment (no IRIS, no Docker daemon available to prove it end to
end). A real deployment puts this behind whatever WSGI/ASGI app the
target platform prefers.
"""

from __future__ import annotations

from typing import Any

from .dbapi import Connection
from .metadata_xml import build_metadata_xml
from .query_translate import build_query, translate_select
from .schema import Schema


class EntitySetNotFound(KeyError):
    pass


def get_metadata_document(schema: Schema) -> str:
    return build_metadata_xml(schema)


def query_entity_set(
    schema: Schema,
    connection: Connection,
    entity_set_name: str,
    *,
    select: str | None = None,
    filter: str | None = None,
    top: str | None = None,
    skip: str | None = None,
    orderby: str | None = None,
) -> list[dict[str, Any]]:
    """Executes one OData-shaped read against `entity_set_name` and
    returns rows as plain dicts keyed by the OData property (= column)
    names that were selected, applying $skip in Python over the
    TOP-bounded SQL result (see query_translate.build_query)."""

    entity_set = schema.entity_set(entity_set_name)
    if entity_set is None:
        raise EntitySetNotFound(entity_set_name)

    query = build_query(
        entity_set, select=select, filter=filter, top=top, skip=skip, orderby=orderby
    )

    cursor = connection.cursor()
    cursor.execute(query.sql, query.params)
    rows = cursor.fetchall()
    if query.skip:
        rows = rows[query.skip :]

    columns = translate_select(entity_set, select)
    return [dict(zip(columns, row)) for row in rows]

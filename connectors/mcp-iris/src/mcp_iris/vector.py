"""IRIS native vector search query builder.

Mirrors the pattern already used elsewhere in this repo (see
``kg-ticket-resolver`` / ``AGENTS.md``'s "Vector Search SQL Pattern"):

    SELECT TOP 8 TicketId, Category, Summary,
           VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE)) sim
    FROM KGTicketResolver_Ticket.Record
    WHERE SummaryVec IS NOT NULL
    ORDER BY sim DESC

This is a *read-only* SQL builder, not a free-text SQL tool: the table,
vector column, and result columns are all identifiers that go through
``identifiers.validate_identifier`` (never string-interpolated without
validation), and the query vector itself is always passed as a bound
parameter to ``TO_VECTOR(?, DOUBLE)`` -- it never touches the SQL text
directly. The resulting SQL is still run through ``sql_guard`` at the
executor layer, as defense in depth, even though this builder cannot
itself produce a write statement.
"""

from __future__ import annotations

from .identifiers import validate_identifier, validate_qualified_name

__all__ = ["vector_search_sql", "MAX_TOP_K"]

# An LLM-driven caller asking for an unbounded top_k is the vector-search
# equivalent of `SELECT *` with no row cap; keep it small independent of
# the executor's general row_cap so a single call can't request a huge
# similarity scan by construction.
MAX_TOP_K = 100


def vector_search_sql(
    table: str,
    vector_column: str,
    query_vector: list[float],
    *,
    select_columns: list[str] | None = None,
    top_k: int = 10,
) -> tuple[str, tuple[str]]:
    validate_qualified_name(table)
    validate_identifier(vector_column)

    if not isinstance(query_vector, list) or not query_vector:
        raise ValueError("query_vector must be a non-empty list of numbers")
    for value in query_vector:
        if not isinstance(value, (int, float)):
            raise ValueError("query_vector must contain only numbers")

    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    if top_k > MAX_TOP_K:
        raise ValueError(f"top_k must be <= {MAX_TOP_K}")

    columns = list(select_columns) if select_columns else []
    for col in columns:
        validate_identifier(col)

    projected = ", ".join(columns) + ", " if columns else ""

    sql = (
        f"SELECT TOP {top_k} {projected}"
        f"VECTOR_COSINE({vector_column}, TO_VECTOR(?, DOUBLE)) AS SIMILARITY "
        f"FROM {table} "
        f"WHERE {vector_column} IS NOT NULL "
        "ORDER BY SIMILARITY DESC"
    )
    vector_param = ",".join(repr(float(v)) for v in query_vector)
    return sql, (vector_param,)

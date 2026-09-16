from __future__ import annotations

import pytest

from mcp_iris.identifiers import InvalidIdentifierError
from mcp_iris.sql_guard import assert_read_only
from mcp_iris.vector import MAX_TOP_K, vector_search_sql


def test_vector_search_sql_basic_shape() -> None:
    sql, params = vector_search_sql(
        "KGTicketResolver_Ticket.Record",
        "SummaryVec",
        [0.1, 0.2, 0.3],
        select_columns=["TicketId", "Category"],
        top_k=8,
    )
    assert "VECTOR_COSINE(SummaryVec, TO_VECTOR(?, DOUBLE))" in sql
    assert "TOP 8" in sql
    assert "TicketId" in sql and "Category" in sql
    assert params == ("0.1,0.2,0.3",)


def test_vector_search_sql_result_is_read_only() -> None:
    sql, _ = vector_search_sql(
        "KGTicketResolver_Ticket.Record", "SummaryVec", [0.1, 0.2]
    )
    # Defense in depth: even a builder that can't produce a write
    # statement must still pass the same guard as free-text queries.
    assert_read_only(sql)


def test_vector_search_sql_rejects_bad_table_name() -> None:
    with pytest.raises(InvalidIdentifierError):
        vector_search_sql("Ticket; DROP TABLE Foo", "SummaryVec", [0.1])


def test_vector_search_sql_rejects_bad_column_name() -> None:
    with pytest.raises(InvalidIdentifierError):
        vector_search_sql("Ticket", "SummaryVec; DROP TABLE Foo", [0.1])


def test_vector_search_sql_rejects_empty_vector() -> None:
    with pytest.raises(ValueError):
        vector_search_sql("Ticket", "SummaryVec", [])


def test_vector_search_sql_rejects_non_numeric_vector() -> None:
    with pytest.raises(ValueError):
        vector_search_sql("Ticket", "SummaryVec", ["a", "b"])  # type: ignore[list-item]


def test_vector_search_sql_rejects_non_positive_top_k() -> None:
    with pytest.raises(ValueError):
        vector_search_sql("Ticket", "SummaryVec", [0.1], top_k=0)


def test_vector_search_sql_rejects_excessive_top_k() -> None:
    with pytest.raises(ValueError):
        vector_search_sql("Ticket", "SummaryVec", [0.1], top_k=MAX_TOP_K + 1)

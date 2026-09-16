from __future__ import annotations

import pytest

from odata_iris.query_translate import (
    ODataQueryError,
    build_query,
    translate_filter,
    translate_orderby,
    translate_select,
    translate_skip,
    translate_top,
)


# ---------------------------------------------------------------------------
# $select
# ---------------------------------------------------------------------------


def test_select_none_returns_all_columns_in_declared_order(patient_entity_set):
    assert translate_select(patient_entity_set, None) == [
        "PatientID",
        "LastName",
        "FirstName",
        "BirthDate",
        "RiskScore",
    ]


def test_select_subset(patient_entity_set):
    assert translate_select(patient_entity_set, "LastName, FirstName") == [
        "LastName",
        "FirstName",
    ]


def test_select_unknown_property_rejected(patient_entity_set):
    with pytest.raises(ODataQueryError):
        translate_select(patient_entity_set, "SocialSecurityNumber")


# ---------------------------------------------------------------------------
# $top / $skip
# ---------------------------------------------------------------------------


def test_top_default_is_reasonable():
    assert translate_top(None) == 100


def test_top_parses_integer():
    assert translate_top("25") == 25


def test_top_rejects_non_integer():
    with pytest.raises(ODataQueryError):
        translate_top("25 OR 1=1")


def test_top_rejects_over_max():
    with pytest.raises(ODataQueryError):
        translate_top("999999")


def test_skip_default_is_zero():
    assert translate_skip(None) == 0


def test_skip_rejects_non_integer():
    with pytest.raises(ODataQueryError):
        translate_skip("-1")


# ---------------------------------------------------------------------------
# $orderby
# ---------------------------------------------------------------------------


def test_orderby_default_direction_is_asc(patient_entity_set):
    assert translate_orderby(patient_entity_set, "LastName") == "LastName ASC"


def test_orderby_explicit_direction(patient_entity_set):
    assert translate_orderby(patient_entity_set, "LastName desc") == "LastName DESC"


def test_orderby_multiple_properties(patient_entity_set):
    assert (
        translate_orderby(patient_entity_set, "LastName desc, FirstName asc")
        == "LastName DESC, FirstName ASC"
    )


def test_orderby_unknown_property_rejected(patient_entity_set):
    with pytest.raises(ODataQueryError):
        translate_orderby(patient_entity_set, "Ssn desc")


def test_orderby_bad_direction_rejected(patient_entity_set):
    with pytest.raises(ODataQueryError):
        translate_orderby(patient_entity_set, "LastName sideways")


# ---------------------------------------------------------------------------
# $filter -> SQL
# ---------------------------------------------------------------------------


def test_filter_simple_equality(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "LastName eq 'Smith'")
    assert sql == "LastName = ?"
    assert params == ["Smith"]


def test_filter_numeric_comparison(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "RiskScore gt 5")
    assert sql == "RiskScore > ?"
    assert params == [5]


def test_filter_and_or_combination(patient_entity_set):
    sql, params = translate_filter(
        patient_entity_set, "LastName eq 'Smith' and RiskScore ge 3"
    )
    assert sql == "(LastName = ? AND RiskScore >= ?)"
    assert params == ["Smith", 3]


def test_filter_or_has_lower_precedence_grouping(patient_entity_set):
    sql, params = translate_filter(
        patient_entity_set,
        "LastName eq 'Smith' or LastName eq 'Jones' and RiskScore gt 1",
    )
    # 'and' binds tighter than 'or', matching OData operator precedence.
    assert sql == "(LastName = ? OR (LastName = ? AND RiskScore > ?))"
    assert params == ["Smith", "Jones", 1]


def test_filter_explicit_parens(patient_entity_set):
    sql, params = translate_filter(
        patient_entity_set, "(LastName eq 'Smith' or LastName eq 'Jones')"
    )
    assert sql == "((LastName = ? OR LastName = ?))"
    assert params == ["Smith", "Jones"]


def test_filter_not(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "not (RiskScore gt 5)")
    assert sql == "(NOT (RiskScore > ?))"
    assert params == [5]


def test_filter_null_eq(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "BirthDate eq null")
    assert sql == "BirthDate IS NULL"
    assert params == []


def test_filter_null_ne(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "BirthDate ne null")
    assert sql == "BirthDate IS NOT NULL"
    assert params == []


def test_filter_contains_function(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "contains(LastName,'mit')")
    assert sql == "LastName LIKE ?"
    assert params == ["%mit%"]


def test_filter_startswith_function(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "startswith(LastName,'Sm')")
    assert sql == "LastName LIKE ?"
    assert params == ["Sm%"]


def test_filter_endswith_function(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "endswith(LastName,'th')")
    assert sql == "LastName LIKE ?"
    assert params == ["%th"]


def test_filter_string_literal_with_escaped_quote(patient_entity_set):
    sql, params = translate_filter(patient_entity_set, "LastName eq 'O''Brien'")
    assert params == ["O'Brien"]


def test_filter_none_returns_none(patient_entity_set):
    assert translate_filter(patient_entity_set, None) == (None, [])


# ---------------------------------------------------------------------------
# build_query — full SELECT assembly
# ---------------------------------------------------------------------------


def test_build_query_basic(patient_entity_set):
    q = build_query(patient_entity_set)
    assert q.sql == (
        "SELECT TOP 100 PatientID, LastName, FirstName, BirthDate, RiskScore "
        "FROM SQLUser.Patient"
    )
    assert q.params == []


def test_build_query_with_select_filter_top_orderby(patient_entity_set):
    q = build_query(
        patient_entity_set,
        select="LastName,FirstName",
        filter="RiskScore gt 3",
        top="10",
        orderby="LastName desc",
    )
    assert q.sql == (
        "SELECT TOP 10 LastName, FirstName FROM SQLUser.Patient "
        "WHERE RiskScore > ? ORDER BY LastName DESC"
    )
    assert q.params == [3]


def test_build_query_top_and_skip_widen_sql_top(patient_entity_set):
    # SQL TOP must cover skip+top rows; the caller slices off the
    # first `skip` rows in Python (IRIS TOP has no paired OFFSET
    # guaranteed here) — see service.py and query.skip.
    q = build_query(patient_entity_set, top="10", skip="5")
    assert q.sql.startswith("SELECT TOP 15 ")
    assert q.skip == 5

"""SQL injection safety for $filter / $select / $orderby / $top / $skip
translation. The properties under test: (1) no client-controlled string
ever appears verbatim inside the generated SQL text unless it exactly
equals a whitelisted column name, and (2) every literal value ends up
in the parameter list, never spliced into the SQL string.
"""

from __future__ import annotations

import pytest

from odata_iris.query_translate import (
    ODataQueryError,
    build_query,
    translate_orderby,
    translate_select,
    translate_top,
)


CLASSIC_PAYLOADS = [
    "'; DROP TABLE SQLUser.Patient; --",
    "' OR '1'='1",
    "x'; DELETE FROM SQLUser.Patient WHERE '1'='1",
    "'/**/UNION/**/SELECT/**/1,2,3,4,5--",
]


@pytest.mark.parametrize("payload", CLASSIC_PAYLOADS)
def test_filter_string_literal_payload_is_parameterized_not_inlined(
    patient_entity_set, payload
):
    from odata_iris.query_translate import translate_filter

    escaped = payload.replace("'", "''")
    sql, params = translate_filter(patient_entity_set, f"LastName eq '{escaped}'")
    assert sql == "LastName = ?"
    assert payload not in sql
    assert params == [payload]


def test_filter_rejects_unknown_identifier_used_as_column(patient_entity_set):
    # An attacker cannot smuggle a second statement or a different table
    # reference through the *property* position either — only names
    # already declared on the entity set are accepted, and the check
    # runs before any SQL text is built with that name.
    with pytest.raises(ODataQueryError):
        from odata_iris.query_translate import translate_filter

        translate_filter(
            patient_entity_set,
            "PatientID eq 1 and (SELECT 1 FROM SQLUser.Secret) eq 1",
        )


def test_filter_rejects_identifier_that_is_not_a_bare_word(patient_entity_set):
    from odata_iris.query_translate import translate_filter

    with pytest.raises(ODataQueryError):
        translate_filter(patient_entity_set, "PatientID; DROP TABLE X eq 1")


def test_select_rejects_injected_column_list(patient_entity_set):
    with pytest.raises(ODataQueryError):
        translate_select(
            patient_entity_set, "PatientID; DROP TABLE SQLUser.Patient;--"
        )


def test_select_rejects_column_from_a_different_table(patient_entity_set):
    with pytest.raises(ODataQueryError):
        translate_select(patient_entity_set, "SocialSecurityNumber")


def test_orderby_rejects_injected_clause(patient_entity_set):
    with pytest.raises(ODataQueryError):
        translate_orderby(patient_entity_set, "LastName; DROP TABLE SQLUser.Patient")


def test_top_rejects_non_numeric_payload():
    with pytest.raises(ODataQueryError):
        translate_top("10; DROP TABLE SQLUser.Patient")


def test_top_rejects_arithmetic_injection_attempt():
    with pytest.raises(ODataQueryError):
        translate_top("10 OR 1=1")


def test_build_query_end_to_end_never_inlines_filter_literal(patient_entity_set):
    q = build_query(
        patient_entity_set,
        filter="LastName eq 'Robert''); DROP TABLE SQLUser.Patient; --'",
    )
    assert "DROP TABLE" not in q.sql
    assert any("DROP TABLE" in str(p) for p in q.params)


def test_build_query_rejects_filter_on_unknown_column_before_any_sql_is_returned(
    patient_entity_set,
):
    with pytest.raises(ODataQueryError):
        build_query(patient_entity_set, filter="Ssn eq '123-45-6789'")

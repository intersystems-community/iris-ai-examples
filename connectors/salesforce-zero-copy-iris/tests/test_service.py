"""End-to-end (still offline) exercise of service.py against a fake
DB-API connection — this is the substitute for a live IRIS instance,
per CLAUDE.md's "no Docker, no live database" constraint in this repo.
A real deployment swaps FakeConnection for `iris.connect(...)`
(intersystems-irispython) without changing service.py or the tests.
"""

from __future__ import annotations

import pytest

from odata_iris.query_translate import ODataQueryError
from odata_iris.service import EntitySetNotFound, get_metadata_document, query_entity_set


class FakeCursor:
    def __init__(self, rows_by_sql):
        self._rows_by_sql = rows_by_sql
        self.last_sql = None
        self.last_params = None
        self._rows: list = []

    def execute(self, sql, params=()):
        self.last_sql = sql
        self.last_params = list(params)
        self._rows = self._rows_by_sql(sql, list(params))

    def fetchall(self):
        return self._rows

    @property
    def description(self):
        return None


class FakeConnection:
    """Minimal stand-in for the odata_iris.dbapi.Connection Protocol."""

    def __init__(self, rows_by_sql):
        self._rows_by_sql = rows_by_sql
        self.cursors: list[FakeCursor] = []

    def cursor(self):
        c = FakeCursor(self._rows_by_sql)
        self.cursors.append(c)
        return c


COLUMN_ORDER = ["PatientID", "LastName", "FirstName", "BirthDate", "RiskScore"]
TABLE = [
    (1, "Smith", "Jane", "1980-01-01", 4.5),
    (2, "Jones", "Bob", "1975-05-05", 2.0),
    (3, "Smith", "Alan", "1990-09-09", 8.1),
]


def _fake_full_table_rows(sql, params):
    """Projects TABLE onto whatever column list the generated SQL asked
    for, the way a real IRIS SELECT would — a naive "always return all
    5 columns" fake would silently pass a $select test for the wrong
    reason (row-tuple position, not column identity)."""

    selected = sql.split("SELECT TOP", 1)[1].split(" FROM", 1)[0]
    selected = selected.split(None, 1)[1]  # drop the "<n>" after TOP
    columns = [c.strip() for c in selected.split(",")]
    indexes = [COLUMN_ORDER.index(c) for c in columns]
    return [tuple(row[i] for i in indexes) for row in TABLE]


def test_query_entity_set_returns_dicts_keyed_by_selected_columns(schema):
    conn = FakeConnection(_fake_full_table_rows)
    rows = query_entity_set(schema, conn, "Patient")
    assert rows[0] == {
        "PatientID": 1,
        "LastName": "Smith",
        "FirstName": "Jane",
        "BirthDate": "1980-01-01",
        "RiskScore": 4.5,
    }
    assert len(rows) == 3


def test_query_entity_set_passes_translated_sql_and_params_to_cursor(schema):
    conn = FakeConnection(_fake_full_table_rows)
    query_entity_set(schema, conn, "Patient", filter="LastName eq 'Smith'", top="5")
    executed = conn.cursors[0]
    assert executed.last_sql == (
        "SELECT TOP 5 PatientID, LastName, FirstName, BirthDate, RiskScore "
        "FROM SQLUser.Patient WHERE LastName = ?"
    )
    assert executed.last_params == ["Smith"]


def test_query_entity_set_applies_select(schema):
    conn = FakeConnection(_fake_full_table_rows)
    rows = query_entity_set(schema, conn, "Patient", select="LastName,FirstName")
    assert rows[0] == {"LastName": "Smith", "FirstName": "Jane"}


def test_query_entity_set_applies_skip_in_python(schema):
    conn = FakeConnection(_fake_full_table_rows)
    rows = query_entity_set(schema, conn, "Patient", top="2", skip="1")
    assert [r["PatientID"] for r in rows] == [2, 3]


def test_query_entity_set_unknown_entity_set_raises(schema):
    conn = FakeConnection(_fake_full_table_rows)
    with pytest.raises(EntitySetNotFound):
        query_entity_set(schema, conn, "NoSuchThing")


def test_query_entity_set_rejects_bad_filter_before_touching_the_connection(schema):
    conn = FakeConnection(_fake_full_table_rows)
    with pytest.raises(ODataQueryError):
        query_entity_set(schema, conn, "Patient", filter="Ssn eq '123'")
    assert conn.cursors == []  # no SQL was ever executed


def test_get_metadata_document_contains_entity_set_name(schema):
    xml_text = get_metadata_document(schema)
    assert "Patient" in xml_text
    assert xml_text.startswith("<?xml")

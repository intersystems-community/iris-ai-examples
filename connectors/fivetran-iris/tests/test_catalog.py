from iris_connector.catalog import build_fivetran_schema, describe_table, discover_schema, list_tables
from iris_connector.fake_db import demo_connection


def test_list_tables_returns_sorted_base_table_names():
    conn = demo_connection()
    assert list_tables(conn, "SQLUser") == ["ENCOUNTER", "PATIENT"]


def test_describe_table_drops_stream_column_and_finds_primary_key():
    conn = demo_connection()
    described = describe_table(conn, "SQLUser", "PATIENT")
    assert described is not None
    assert "CHART_NOTE" not in described.column_names  # LONGVARCHAR is dropped
    assert described.primary_key == ["PATIENT_ID"]
    assert described.fivetran_types["PATIENT_ID"] == "LONG"
    assert described.fivetran_types["NAME"] == "STRING"
    assert described.fivetran_types["BIRTH_DATE"] == "NAIVE_DATE"
    assert described.fivetran_types["LAST_UPDATED"] == "NAIVE_DATETIME"
    assert described.fivetran_types["HEIGHT_CM"] == {"type": "DECIMAL", "precision": 5, "scale": 1}
    assert described.fivetran_types["IS_ACTIVE"] == "BOOLEAN"


def test_describe_table_maps_posixtime_column():
    conn = demo_connection()
    described = describe_table(conn, "SQLUser", "ENCOUNTER")
    assert described.fivetran_types["VISIT_AT"] == "UTC_DATETIME"


def test_describe_missing_table_returns_none():
    conn = demo_connection()
    assert describe_table(conn, "SQLUser", "NOPE") is None


def test_discover_schema_respects_table_allowlist():
    conn = demo_connection()
    tables = discover_schema(conn, "SQLUser", table_allowlist=["PATIENT"])
    assert [t.table_name for t in tables] == ["PATIENT"]


def test_discover_schema_warns_about_unknown_allowlist_table():
    conn = demo_connection()
    warnings = []
    discover_schema(conn, "SQLUser", table_allowlist=["NOPE"], warn=warnings.append)
    assert any("NOPE" in w for w in warnings)


def test_build_fivetran_schema_shape_matches_sdk_contract():
    """`fivetran_connector_sdk.connector_helper.process_tables` requires each
    entry to have a "table" key and, if present, "primary_key" (list) and
    "columns" (dict of name -> type-string-or-decimal-dict). This test
    locks in that exact shape independent of the SDK being installed.
    """
    conn = demo_connection()
    tables = discover_schema(conn, "SQLUser")
    schema_defs = build_fivetran_schema(tables)

    by_name = {entry["table"]: entry for entry in schema_defs}
    assert set(by_name) == {"PATIENT", "ENCOUNTER"}

    patient = by_name["PATIENT"]
    assert patient["primary_key"] == ["PATIENT_ID"]
    assert isinstance(patient["columns"], dict)
    assert "CHART_NOTE" not in patient["columns"]
    assert patient["columns"]["PATIENT_ID"] == "LONG"

    for entry in schema_defs:
        assert isinstance(entry["table"], str)
        assert isinstance(entry["columns"], dict)
        for col_type in entry["columns"].values():
            assert isinstance(col_type, str) or (
                isinstance(col_type, dict) and col_type.get("type") == "DECIMAL"
            )

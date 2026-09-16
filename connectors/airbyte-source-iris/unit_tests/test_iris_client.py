from source_iris.iris_client import DEFAULT_EXCLUDED_SCHEMAS, IrisClient


class TestTestConnection:
    def test_succeeds_against_fake(self, fake_connection):
        IrisClient(fake_connection).test_connection()  # must not raise

    def test_raises_on_query_failure(self, sample_tables_catalog, sample_columns_catalog, sample_table_data):
        from .fakes import FakeIrisConnection

        conn = FakeIrisConnection(
            tables_catalog=sample_tables_catalog,
            columns_catalog=sample_columns_catalog,
            table_data=sample_table_data,
            fail_test_query=True,
        )
        import pytest

        with pytest.raises(RuntimeError):
            IrisClient(conn).test_connection()


class TestListTables:
    def test_excludes_system_schemas_by_default(self, fake_connection):
        tables = IrisClient(fake_connection).list_tables()
        names = {(t.schema, t.name) for t in tables}
        assert ("%SYS", "Config") not in names
        assert "%SYS" in DEFAULT_EXCLUDED_SCHEMAS

    def test_discovers_expected_tables(self, fake_connection):
        tables = IrisClient(fake_connection).list_tables()
        names = sorted((t.schema, t.name) for t in tables)
        assert names == [("SQLUser", "Note"), ("SQLUser", "Patient")]

    def test_explicit_schema_filter_bypasses_exclusion_list(self, fake_connection):
        # If the user explicitly asks for a schema, honor it even if it would
        # otherwise be excluded by default (e.g. they really do want %SYS).
        tables = IrisClient(fake_connection).list_tables(schemas=["%SYS"])
        names = {(t.schema, t.name) for t in tables}
        assert ("%SYS", "Config") in names

    def test_columns_populated_with_primary_key_flag(self, fake_connection):
        tables = IrisClient(fake_connection).list_tables()
        patient = next(t for t in tables if t.name == "Patient")
        by_name = {c.name: c for c in patient.columns}
        assert by_name["ID"].is_primary_key is True
        assert by_name["NAME"].is_primary_key is False
        assert patient.primary_key == ["ID"]

    def test_table_without_primary_key(self, fake_connection):
        tables = IrisClient(fake_connection).list_tables()
        note = next(t for t in tables if t.name == "Note")
        assert note.primary_key == []

    def test_lob_column_flagged(self, fake_connection):
        tables = IrisClient(fake_connection).list_tables()
        patient = next(t for t in tables if t.name == "Patient")
        notes_col = next(c for c in patient.columns if c.name == "NOTES")
        assert notes_col.is_lob is True

    def test_uses_bound_parameters_not_string_interpolation_for_schema_filter(self, fake_connection):
        IrisClient(fake_connection).list_tables(schemas=["SQLUser"])
        sql, params = next(
            stmt for stmt in fake_connection.executed_statements if "INFORMATION_SCHEMA.TABLES" in stmt[0]
        )
        assert "SQLUser" not in sql  # the schema name must never be spliced into the SQL text
        assert params == ["SQLUser"]


class TestReadFullRefresh:
    def test_reads_all_rows_in_requested_columns(self, fake_connection):
        rows = list(IrisClient(fake_connection).read_full_refresh("SQLUser", "Note", ["NOTE_ID", "BODY"]))
        assert rows == [
            {"NOTE_ID": 10, "BODY": "first"},
            {"NOTE_ID": 11, "BODY": "second"},
        ]

    def test_respects_requested_column_subset_and_order(self, fake_connection):
        rows = list(IrisClient(fake_connection).read_full_refresh("SQLUser", "Note", ["BODY"]))
        assert rows == [{"BODY": "first"}, {"BODY": "second"}]

    def test_generated_sql_quotes_identifiers(self, fake_connection):
        list(IrisClient(fake_connection).read_full_refresh("SQLUser", "Note", ["NOTE_ID"]))
        sql, _params = fake_connection.executed_statements[-1]
        assert '"SQLUser"."Note"' in sql
        assert '"NOTE_ID"' in sql


class TestReadIncremental:
    def test_first_sync_with_no_state_reads_everything_in_cursor_order(self, fake_connection):
        rows = list(
            IrisClient(fake_connection).read_incremental(
                "SQLUser", "Patient", ["ID", "NAME"], cursor_field="ID", cursor_value=None
            )
        )
        assert [r["ID"] for r in rows] == [1, 2, 3]

    def test_resumes_strictly_after_cursor_value(self, fake_connection):
        rows = list(
            IrisClient(fake_connection).read_incremental(
                "SQLUser", "Patient", ["ID", "NAME"], cursor_field="ID", cursor_value=1
            )
        )
        assert [r["ID"] for r in rows] == [2, 3]

    def test_cursor_value_passed_as_bound_parameter(self, fake_connection):
        list(
            IrisClient(fake_connection).read_incremental(
                "SQLUser", "Patient", ["ID"], cursor_field="ID", cursor_value=1
            )
        )
        sql, params = fake_connection.executed_statements[-1]
        assert "?" in sql
        assert 1 in params
        # the literal value must never be spliced into the SQL text itself
        assert " 1" not in sql.replace("SELECT", "").replace('"ID"', "")

    def test_orders_ascending_by_cursor(self, fake_connection):
        # data fixture is already ascending; assert the ORDER BY clause is present so
        # a future re-ordering of the fixture would still be caught.
        list(
            IrisClient(fake_connection).read_incremental(
                "SQLUser", "Patient", ["ID"], cursor_field="ID", cursor_value=None
            )
        )
        sql, _params = fake_connection.executed_statements[-1]
        assert "ORDER BY" in sql.upper()

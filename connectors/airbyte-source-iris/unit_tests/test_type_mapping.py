from source_iris.type_mapping import is_lob_type, map_iris_type, quote_ident, quote_qualified


class TestQuoteIdent:
    def test_wraps_in_double_quotes(self):
        assert quote_ident("Patient") == '"Patient"'

    def test_escapes_embedded_double_quotes(self):
        # A hostile/unusual identifier must not be able to break out of its quoting.
        assert quote_ident('Robert"; DROP TABLE Patient; --') == '"Robert""; DROP TABLE Patient; --"'

    def test_none_raises(self):
        import pytest

        with pytest.raises(ValueError):
            quote_ident(None)

    def test_quote_qualified(self):
        assert quote_qualified("SQLUser", "Patient") == '"SQLUser"."Patient"'


class TestMapIrisType:
    def test_bigint_maps_to_integer_with_big_integer_marker(self):
        result = map_iris_type("BIGINT", is_nullable=False)
        assert result["type"] == "integer"
        assert result["airbyte_type"] == "big_integer"

    def test_varchar_maps_to_string(self):
        result = map_iris_type("VARCHAR", is_nullable=False)
        assert result == {"type": "string"}

    def test_nullable_column_gets_null_in_type_union(self):
        result = map_iris_type("VARCHAR", is_nullable=True)
        assert result["type"] == ["string", "null"]

    def test_not_nullable_column_has_scalar_type(self):
        result = map_iris_type("VARCHAR", is_nullable=False)
        assert result["type"] == "string"

    def test_timestamp_maps_to_date_time_string(self):
        # Covers both %TimeStamp and %PosixTime, which are indistinguishable at the
        # INFORMATION_SCHEMA.COLUMNS level: both report DATA_TYPE = 'TIMESTAMP' (their
        # documented ODBC type). See README.md for what this means for %PosixTime.
        result = map_iris_type("TIMESTAMP", is_nullable=False)
        assert result["type"] == "string"
        assert result["format"] == "date-time"

    def test_date_maps_to_date_string(self):
        result = map_iris_type("DATE", is_nullable=False)
        assert result["type"] == "string"
        assert result["format"] == "date"

    def test_high_precision_decimal_marked_big_number(self):
        result = map_iris_type("DECIMAL", is_nullable=False, numeric_precision=30, numeric_scale=4)
        assert result["type"] == "number"
        assert result["airbyte_type"] == "big_number"

    def test_high_precision_zero_scale_numeric_marked_big_integer(self):
        result = map_iris_type("NUMERIC", is_nullable=False, numeric_precision=30, numeric_scale=0)
        assert result["type"] == "number"
        assert result["airbyte_type"] == "big_integer"

    def test_low_precision_decimal_has_no_airbyte_type_marker(self):
        result = map_iris_type("DECIMAL", is_nullable=False, numeric_precision=10, numeric_scale=2)
        assert "airbyte_type" not in result

    def test_unknown_type_falls_back_to_string(self):
        # discover() must not blow up on a column type this connector has never heard
        # of; it degrades to a plain string rather than raising.
        result = map_iris_type("SOME_FUTURE_IRIS_TYPE", is_nullable=False)
        assert result == {"type": "string"}

    def test_lob_types_flagged(self):
        assert is_lob_type("LONGVARCHAR") is True
        assert is_lob_type("LONGVARBINARY") is True
        assert is_lob_type("VARCHAR") is False
        assert is_lob_type(None) is False

    def test_case_insensitive(self):
        assert map_iris_type("varchar", is_nullable=False) == {"type": "string"}

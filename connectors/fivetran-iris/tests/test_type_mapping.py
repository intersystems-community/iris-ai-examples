import pytest

from iris_connector.type_mapping import MAX_DECIMAL_PRECISION, map_iris_type


@pytest.mark.parametrize(
    "iris_type,expected",
    [
        ("BIGINT", "LONG"),
        ("INTEGER", "INT"),
        ("INT", "INT"),
        ("SMALLINT", "SHORT"),
        ("TINYINT", "SHORT"),
        ("BIT", "BOOLEAN"),
        ("DOUBLE", "DOUBLE"),
        ("FLOAT", "DOUBLE"),
        ("VARCHAR", "STRING"),
        ("CHAR", "STRING"),
        ("GUID", "STRING"),
        ("DATE", "NAIVE_DATE"),
        ("TIMESTAMP", "NAIVE_DATETIME"),
        ("POSIXTIME", "UTC_DATETIME"),
        ("VARBINARY", "BINARY"),
        ("BINARY", "BINARY"),
        ("TIME", "STRING"),
    ],
)
def test_simple_type_mappings(iris_type, expected):
    assert map_iris_type(iris_type) == expected


def test_mapping_is_case_insensitive():
    assert map_iris_type("varchar") == "STRING"
    assert map_iris_type("BigInt") == "LONG"


@pytest.mark.parametrize("dropped_type", ["LONGVARCHAR", "LONGVARBINARY", "OREF"])
def test_dropped_types_return_none_and_warn(dropped_type):
    warnings = []
    result = map_iris_type(dropped_type, warn=warnings.append, context="T.C")
    assert result is None
    assert len(warnings) == 1
    assert "T.C" in warnings[0]


def test_numeric_maps_to_decimal_with_precision_and_scale():
    result = map_iris_type("NUMERIC", numeric_precision=10, numeric_scale=2)
    assert result == {"type": "DECIMAL", "precision": 10, "scale": 2}


def test_numeric_without_precision_defaults_and_warns():
    warnings = []
    result = map_iris_type("NUMERIC", numeric_precision=None, numeric_scale=None, warn=warnings.append)
    assert result == {"type": "DECIMAL", "precision": MAX_DECIMAL_PRECISION, "scale": 0}
    assert any("NUMERIC_PRECISION" in w for w in warnings)


def test_numeric_precision_is_clamped_to_max_and_warns():
    warnings = []
    result = map_iris_type("NUMERIC", numeric_precision=50, numeric_scale=2, warn=warnings.append)
    assert result == {"type": "DECIMAL", "precision": MAX_DECIMAL_PRECISION, "scale": 2}
    assert any("exceeds this connector's cap" in w for w in warnings)


def test_numeric_scale_greater_than_precision_is_clamped():
    warnings = []
    result = map_iris_type("NUMERIC", numeric_precision=5, numeric_scale=9, warn=warnings.append)
    assert result == {"type": "DECIMAL", "precision": 5, "scale": 5}
    assert any("exceeds NUMERIC_PRECISION" in w for w in warnings)


def test_unrecognized_type_falls_back_to_string_and_warns():
    warnings = []
    result = map_iris_type("SOME_FUTURE_TYPE", warn=warnings.append, context="T.C")
    assert result == "STRING"
    assert any("unrecognized" in w for w in warnings)


def test_none_data_type_returns_none_and_warns():
    warnings = []
    result = map_iris_type(None, warn=warnings.append)
    assert result is None
    assert len(warnings) == 1


def test_warn_is_optional_and_defaults_to_silent():
    # Must not raise even though warn is not supplied.
    assert map_iris_type("LONGVARCHAR") is None
    assert map_iris_type("SOME_FUTURE_TYPE") == "STRING"

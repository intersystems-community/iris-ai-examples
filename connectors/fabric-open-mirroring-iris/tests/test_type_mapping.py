from __future__ import annotations

import pyarrow as pa
import pytest

from fabric_open_mirroring_iris.iris_types import (
    ColumnDef,
    UnsupportedIrisTypeError,
    iris_column_to_arrow_field,
    iris_schema_to_arrow,
)


@pytest.mark.parametrize(
    "iris_type,expected_arrow_type",
    [
        ("BIGINT", pa.int64()),
        ("INTEGER", pa.int32()),
        ("SMALLINT", pa.int16()),
        ("TINYINT", pa.int8()),
        ("DOUBLE", pa.float64()),
        ("REAL", pa.float32()),
        ("VARCHAR", pa.string()),
        ("LONGVARCHAR", pa.string()),
        ("DATE", pa.date32()),
        ("TIME", pa.time64("us")),
        ("TIMESTAMP", pa.timestamp("us")),
        ("BIT", pa.bool_()),
        ("VARBINARY", pa.binary()),
        ("GUID", pa.string()),
    ],
)
def test_simple_type_mapping(iris_type, expected_arrow_type):
    col = ColumnDef(name="c", iris_type=iris_type)
    field = iris_column_to_arrow_field(col)
    assert field.type == expected_arrow_type
    assert field.name == "c"


def test_date_maps_to_date32_not_date64():
    # Fabric's Parquet constraint check requires physical INT32 for a
    # logical DATE column; pa.date32() is the Arrow type that PyArrow's
    # Parquet writer serializes with that physical/logical combination.
    field = iris_column_to_arrow_field(ColumnDef(name="d", iris_type="DATE"))
    assert field.type == pa.date32()
    assert field.type != pa.date64()


def test_numeric_uses_declared_precision_and_scale():
    col = ColumnDef(name="amount", iris_type="NUMERIC", precision=12, scale=4)
    field = iris_column_to_arrow_field(col)
    assert field.type == pa.decimal128(12, 4)


def test_numeric_falls_back_to_documented_default_when_precision_missing():
    col = ColumnDef(name="amount", iris_type="NUMERIC")
    field = iris_column_to_arrow_field(col)
    assert field.type == pa.decimal128(38, 10)


def test_nullability_is_preserved():
    col = ColumnDef(name="c", iris_type="VARCHAR", nullable=False)
    field = iris_column_to_arrow_field(col)
    assert field.nullable is False


def test_unsupported_list_type_raises_with_explanation():
    col = ColumnDef(name="tags", iris_type="LIST")
    with pytest.raises(UnsupportedIrisTypeError) as exc:
        iris_column_to_arrow_field(col)
    assert "tags" in str(exc.value)
    assert "$LISTBUILD" in str(exc.value)


def test_unsupported_object_type_raises():
    col = ColumnDef(name="related", iris_type="OBJECT")
    with pytest.raises(UnsupportedIrisTypeError):
        iris_column_to_arrow_field(col)


def test_unknown_type_falls_back_to_string_rather_than_dropping_silently():
    col = ColumnDef(name="mystery", iris_type="SOME_FUTURE_TYPE")
    field = iris_column_to_arrow_field(col)
    assert field.type == pa.string()


def test_schema_to_arrow_raises_by_default_on_unsupported_column():
    cols = [ColumnDef("id", "BIGINT"), ColumnDef("tags", "LIST")]
    with pytest.raises(UnsupportedIrisTypeError):
        iris_schema_to_arrow(cols)


def test_schema_to_arrow_can_skip_unsupported_columns():
    cols = [ColumnDef("id", "BIGINT"), ColumnDef("tags", "LIST")]
    schema = iris_schema_to_arrow(cols, skip_unsupported=True)
    assert schema.names == ["id"]

from __future__ import annotations

import json
import re

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from fabric_open_mirroring_iris.landing_zone import (
    KeyColumnsImmutableError,
    OpenMirroringLandingZoneWriter,
    SEQUENCE_FILENAME_RE,
    build_arrow_table,
    relax_nullability_for_incremental,
    with_row_marker_field,
)

DATA_SCHEMA = pa.schema([pa.field("id", pa.int64()), pa.field("name", pa.string())])


def test_metadata_file_written_with_key_columns(writer):
    path = writer.ensure_table_metadata("Patient", ["PatientID"])
    assert path.name == "_metadata.json"
    payload = json.loads(path.read_text())
    assert payload["keyColumns"] == ["PatientID"]


def test_metadata_file_location_matches_table_folder(landing_zone_root, writer):
    writer.ensure_table_metadata("Patient", ["PatientID"])
    expected = landing_zone_root / "Patient" / "_metadata.json"
    assert expected.exists()


def test_metadata_with_schema_uses_schema_dot_schema_folder(landing_zone_root, writer):
    writer.ensure_table_metadata("Patient", ["PatientID"], schema="dbo")
    expected = landing_zone_root / "dbo.schema" / "Patient" / "_metadata.json"
    assert expected.exists()


def test_key_columns_are_immutable_once_set(writer):
    writer.ensure_table_metadata("Patient", ["PatientID"])
    with pytest.raises(KeyColumnsImmutableError):
        writer.ensure_table_metadata("Patient", ["PatientID", "MRN"])


def test_ensure_metadata_is_idempotent_when_unchanged(writer):
    p1 = writer.ensure_table_metadata("Patient", ["PatientID"])
    mtime1 = p1.stat().st_mtime_ns
    p2 = writer.ensure_table_metadata("Patient", ["PatientID"])
    assert p1 == p2
    # Second call must not rewrite an unchanged file (no unnecessary churn).
    assert p2.stat().st_mtime_ns == mtime1


def test_partner_events_written_at_landing_zone_root(landing_zone_root, writer):
    path = writer.write_partner_events(
        partner_name="iris-open-mirroring", source_type="IRIS", source_version="2025.1"
    )
    assert path == landing_zone_root / "_partnerEvents.json"
    payload = json.loads(path.read_text())
    assert payload["partnerName"] == "iris-open-mirroring"
    assert payload["sourceInfo"]["sourceType"] == "IRIS"


def test_first_data_file_is_sequence_one(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    table = build_arrow_table(DATA_SCHEMA, [{"id": 1, "name": "a"}])
    wf = writer.write_batch("Patient", table, is_initial_load=True)
    assert wf.sequence_number == 1
    assert wf.path.name == "00000000000000000001.parquet"
    assert len(wf.path.name.split(".")[0]) == 20


def test_filename_matches_documented_pattern(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    table = build_arrow_table(DATA_SCHEMA, [{"id": 1, "name": "a"}])
    wf = writer.write_batch("Patient", table, is_initial_load=True)
    assert SEQUENCE_FILENAME_RE.match(wf.path.name)
    assert re.fullmatch(r"\d{20}\.parquet", wf.path.name)


def test_sequence_numbers_increase_monotonically_across_batches(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    seqs = []
    for i in range(5):
        table = build_arrow_table(DATA_SCHEMA, [{"id": i, "name": f"row{i}"}])
        wf = writer.write_batch("Patient", table, is_initial_load=True)
        seqs.append(wf.sequence_number)
    assert seqs == [1, 2, 3, 4, 5]


def test_no_temp_files_left_behind_after_write(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    table = build_arrow_table(DATA_SCHEMA, [{"id": 1, "name": "a"}])
    wf = writer.write_batch("Patient", table, is_initial_load=True)
    leftovers = [p for p in wf.path.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_initial_load_batch_rejects_row_marker_column(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    marker_schema = with_row_marker_field(DATA_SCHEMA)
    table = build_arrow_table(marker_schema, [{"id": 1, "name": "a", "__rowMarker__": 0}])
    with pytest.raises(ValueError, match="must not include"):
        writer.write_batch("Patient", table, is_initial_load=True)


def test_incremental_batch_requires_row_marker_column(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    table = build_arrow_table(DATA_SCHEMA, [{"id": 1, "name": "a"}])
    with pytest.raises(ValueError, match="must include __rowMarker__"):
        writer.write_batch("Patient", table, is_initial_load=False)


def test_row_marker_must_be_last_column(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    bad_schema = pa.schema(
        [pa.field("__rowMarker__", pa.int32()), pa.field("id", pa.int64())]
    )
    table = build_arrow_table(bad_schema, [{"id": 1, "__rowMarker__": 0}])
    with pytest.raises(ValueError, match="last column"):
        writer.write_batch("Patient", table, is_initial_load=False)


def test_relax_nullability_keeps_key_columns_strict_and_relaxes_others():
    schema = pa.schema(
        [
            pa.field("id", pa.int64(), nullable=False),
            pa.field("mrn", pa.string(), nullable=False),
        ]
    )
    relaxed = relax_nullability_for_incremental(schema, key_columns=["id"])
    assert relaxed.field("id").nullable is False
    assert relaxed.field("mrn").nullable is True


def test_written_parquet_is_readable_with_expected_schema(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    table = build_arrow_table(DATA_SCHEMA, [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}])
    wf = writer.write_batch("Patient", table, is_initial_load=True)

    read_back = pq.read_table(wf.path)
    assert read_back.schema.equals(DATA_SCHEMA)
    assert read_back.to_pylist() == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]


def test_incremental_file_readable_with_row_marker_last(writer):
    writer.ensure_table_metadata("Patient", ["id"])
    marker_schema = with_row_marker_field(DATA_SCHEMA)
    rows = [{"id": 1, "name": "alice", "__rowMarker__": 4}]
    table = build_arrow_table(marker_schema, rows)
    wf = writer.write_batch("Patient", table, is_initial_load=False)

    read_back = pq.read_table(wf.path)
    assert read_back.schema.names[-1] == "__rowMarker__"
    assert read_back.to_pylist() == rows

from airbyte_cdk.models import SyncMode

from source_iris.iris_client import IrisClient
from source_iris.streams import IrisTableStream


def _patient_table(fake_connection):
    tables = IrisClient(fake_connection).list_tables()
    return next(t for t in tables if t.name == "Patient")


def _note_table(fake_connection):
    tables = IrisClient(fake_connection).list_tables()
    return next(t for t in tables if t.name == "Note")


class TestStreamIdentity:
    def test_name_is_schema_qualified(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        assert stream.name == "SQLUser_Patient"
        assert stream.namespace == "SQLUser"

    def test_primary_key_single_column(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        assert stream.primary_key == "ID"

    def test_primary_key_none_when_table_has_none(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _note_table(fake_connection), cursor_field=None)
        assert stream.primary_key is None

    def test_supports_incremental_true_when_cursor_field_set(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        assert stream.supports_incremental is True

    def test_supports_incremental_false_without_cursor_field(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _note_table(fake_connection), cursor_field=None)
        assert stream.supports_incremental is False


class TestStreamFullRefreshRead:
    def test_read_records_full_refresh(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _note_table(fake_connection), cursor_field=None)
        records = list(stream.read_records(sync_mode=SyncMode.full_refresh))
        assert records == [{"NOTE_ID": 10, "BODY": "first"}, {"NOTE_ID": 11, "BODY": "second"}]


class TestStreamIncrementalRead:
    def test_read_records_incremental_from_scratch(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        records = list(stream.read_records(sync_mode=SyncMode.incremental, stream_state={}))
        assert [r["ID"] for r in records] == [1, 2, 3]

    def test_state_advances_as_records_are_read(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        list(stream.read_records(sync_mode=SyncMode.incremental, stream_state={}))
        assert stream.state == {"ID": 3}

    def test_read_records_incremental_resumes_from_state(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        records = list(stream.read_records(sync_mode=SyncMode.incremental, stream_state={"ID": 1}))
        assert [r["ID"] for r in records] == [2, 3]

    def test_state_setter_replaces_state(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        stream.state = {"ID": 42}
        assert stream.state == {"ID": 42}

    def test_get_json_schema_includes_all_columns(self, fake_connection):
        stream = IrisTableStream(IrisClient(fake_connection), _patient_table(fake_connection), cursor_field="ID")
        schema = stream.get_json_schema()
        assert set(schema["properties"]) == {"ID", "NAME", "UPDATED_AT", "NOTES"}

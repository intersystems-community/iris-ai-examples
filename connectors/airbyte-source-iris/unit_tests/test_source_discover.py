import logging

from airbyte_cdk.models import SyncMode

from source_iris.source import IrisSource

from .conftest import VALID_CONFIG

logger = logging.getLogger("test")


class TestDiscover:
    def test_discover_returns_one_stream_per_table(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        catalog = source.discover(logger, VALID_CONFIG)
        names = {s.name for s in catalog.streams}
        assert names == {"SQLUser_Patient", "SQLUser_Note"}

    def test_table_with_single_column_pk_supports_incremental(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        catalog = source.discover(logger, VALID_CONFIG)
        patient = next(s for s in catalog.streams if s.name == "SQLUser_Patient")
        assert SyncMode.full_refresh in patient.supported_sync_modes
        assert SyncMode.incremental in patient.supported_sync_modes
        assert patient.default_cursor_field == ["ID"]
        assert patient.source_defined_primary_key == [["ID"]]

    def test_table_without_pk_is_full_refresh_only(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        catalog = source.discover(logger, VALID_CONFIG)
        note = next(s for s in catalog.streams if s.name == "SQLUser_Note")
        assert note.supported_sync_modes == [SyncMode.full_refresh]
        assert not note.source_defined_primary_key

    def test_json_schema_reflects_column_types_and_nullability(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        catalog = source.discover(logger, VALID_CONFIG)
        patient = next(s for s in catalog.streams if s.name == "SQLUser_Patient")
        props = patient.json_schema["properties"]
        assert props["ID"]["type"] == "integer"  # NOT NULL primary key -> no null union
        assert props["NAME"]["type"] == ["string", "null"]  # nullable varchar
        assert props["UPDATED_AT"]["format"] == "date-time"
        # LOB column still shows up (best-effort string), documented as such.
        assert props["NOTES"]["type"] == ["string", "null"]

    def test_namespace_set_to_iris_schema(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        catalog = source.discover(logger, VALID_CONFIG)
        for stream in catalog.streams:
            assert stream.namespace == "SQLUser"

    def test_tables_config_filter_restricts_discovery(self, fake_connection):
        source = IrisSource(connection_factory=lambda config: fake_connection)
        config = dict(VALID_CONFIG, tables=["Patient"])
        catalog = source.discover(logger, config)
        assert {s.name for s in catalog.streams} == {"SQLUser_Patient"}

    def test_discover_via_airbyte_entrypoint(self, connection_factory, tmp_path):
        # Runs the real CDK CLI entrypoint (AirbyteEntrypoint), not just our own
        # Python API, to prove `discover` works as the platform would invoke it.
        import json

        from airbyte_cdk.entrypoint import AirbyteEntrypoint

        source = IrisSource(connection_factory=connection_factory)
        entrypoint = AirbyteEntrypoint(source)

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(VALID_CONFIG))

        parsed = entrypoint.parse_args(["discover", "--config", str(config_path)])
        messages = [json.loads(m) for m in entrypoint.run(parsed) if m.strip()]
        catalog_messages = [m for m in messages if m.get("type") == "CATALOG"]
        assert len(catalog_messages) == 1
        stream_names = {s["name"] for s in catalog_messages[0]["catalog"]["streams"]}
        assert stream_names == {"SQLUser_Patient", "SQLUser_Note"}

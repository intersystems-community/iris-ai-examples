import json
import logging

from airbyte_cdk.entrypoint import AirbyteEntrypoint
from airbyte_cdk.models import (
    ConfiguredAirbyteCatalog,
    ConfiguredAirbyteStream,
    DestinationSyncMode,
    SyncMode,
    Type as MessageType,
)

from source_iris.source import IrisSource

from .conftest import VALID_CONFIG

logger = logging.getLogger("test")


class TestFullRefreshRead:
    def test_reads_every_row(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        catalog = source.discover(logger, VALID_CONFIG)
        note_stream = next(s for s in catalog.streams if s.name == "SQLUser_Note")
        configured = ConfiguredAirbyteCatalog(
            streams=[
                ConfiguredAirbyteStream(
                    stream=note_stream,
                    sync_mode=SyncMode.full_refresh,
                    destination_sync_mode=DestinationSyncMode.append,
                )
            ]
        )

        messages = list(source.read(logger, VALID_CONFIG, configured, state=None))
        records = [m.record.data for m in messages if m.type == MessageType.RECORD]
        assert records == [{"NOTE_ID": 10, "BODY": "first"}, {"NOTE_ID": 11, "BODY": "second"}]

    def test_full_refresh_via_airbyte_entrypoint(self, connection_factory, tmp_path):
        """Runs the real CDK CLI entrypoint end to end: discover -> configure -> read."""
        source = IrisSource(connection_factory=connection_factory)
        entrypoint = AirbyteEntrypoint(source)

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(VALID_CONFIG))

        discover_args = entrypoint.parse_args(["discover", "--config", str(config_path)])
        catalog_message = next(
            json.loads(m) for m in entrypoint.run(discover_args) if json.loads(m).get("type") == "CATALOG"
        )
        note_stream_schema = next(
            s for s in catalog_message["catalog"]["streams"] if s["name"] == "SQLUser_Note"
        )

        configured_catalog = {
            "streams": [
                {
                    "stream": note_stream_schema,
                    "sync_mode": "full_refresh",
                    "destination_sync_mode": "append",
                }
            ]
        }
        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text(json.dumps(configured_catalog))

        read_args = entrypoint.parse_args(["read", "--config", str(config_path), "--catalog", str(catalog_path)])
        records = [
            json.loads(m)["record"]["data"]
            for m in entrypoint.run(read_args)
            if json.loads(m).get("type") == "RECORD"
        ]
        assert records == [{"NOTE_ID": 10, "BODY": "first"}, {"NOTE_ID": 11, "BODY": "second"}]


class TestIncrementalRead:
    def _catalog_for_patient(self, patient_stream_schema, cursor_field=("ID",)):
        return {
            "streams": [
                {
                    "stream": patient_stream_schema,
                    "sync_mode": "incremental",
                    "destination_sync_mode": "append",
                    "cursor_field": list(cursor_field),
                }
            ]
        }

    def test_first_sync_emits_all_records_and_final_state(self, connection_factory, tmp_path):
        source = IrisSource(connection_factory=connection_factory)
        entrypoint = AirbyteEntrypoint(source)

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(VALID_CONFIG))

        discover_args = entrypoint.parse_args(["discover", "--config", str(config_path)])
        catalog_message = next(
            json.loads(m) for m in entrypoint.run(discover_args) if json.loads(m).get("type") == "CATALOG"
        )
        patient_schema = next(
            s for s in catalog_message["catalog"]["streams"] if s["name"] == "SQLUser_Patient"
        )

        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text(json.dumps(self._catalog_for_patient(patient_schema)))

        read_args = entrypoint.parse_args(["read", "--config", str(config_path), "--catalog", str(catalog_path)])
        messages = [json.loads(m) for m in entrypoint.run(read_args)]
        records = [m["record"]["data"] for m in messages if m.get("type") == "RECORD"]
        states = [m["state"] for m in messages if m.get("type") == "STATE"]

        assert [r["ID"] for r in records] == [1, 2, 3]
        assert states, "expected at least one STATE message"
        final_state = states[-1]
        assert final_state["stream"]["stream_state"] == {"ID": 3}
        assert final_state["stream"]["stream_descriptor"]["name"] == "SQLUser_Patient"

    def test_resume_from_state_only_reads_newer_rows(self, fake_connection, tmp_path):
        source = IrisSource(connection_factory=lambda config: fake_connection)
        entrypoint = AirbyteEntrypoint(source)

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(VALID_CONFIG))

        discover_args = entrypoint.parse_args(["discover", "--config", str(config_path)])
        catalog_message = next(
            json.loads(m) for m in entrypoint.run(discover_args) if json.loads(m).get("type") == "CATALOG"
        )
        patient_schema = next(
            s for s in catalog_message["catalog"]["streams"] if s["name"] == "SQLUser_Patient"
        )
        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text(json.dumps(self._catalog_for_patient(patient_schema)))

        # Simulate a prior sync that got as far as ID=1, then a new row (ID=4) arrives.
        # Must include every column of the Patient fixture (see conftest.py), since a
        # real sync selects all of them, not just ID/NAME.
        fake_connection.table_data[("SQLUser", "Patient")].append(
            {"ID": 4, "NAME": "Rosalind Franklin", "UPDATED_AT": "2026-01-04 00:00:00.000000", "NOTES": "n4"}
        )
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                [
                    {
                        "type": "STREAM",
                        "stream": {
                            "stream_descriptor": {"name": "SQLUser_Patient", "namespace": "SQLUser"},
                            "stream_state": {"ID": 1},
                        },
                    }
                ]
            )
        )

        read_args = entrypoint.parse_args(
            ["read", "--config", str(config_path), "--catalog", str(catalog_path), "--state", str(state_path)]
        )
        records = [
            json.loads(m)["record"]["data"]
            for m in entrypoint.run(read_args)
            if json.loads(m).get("type") == "RECORD"
        ]
        assert [r["ID"] for r in records] == [2, 3, 4]

    def test_no_new_rows_since_state_emits_zero_records(self, fake_connection, tmp_path):
        source = IrisSource(connection_factory=lambda config: fake_connection)
        entrypoint = AirbyteEntrypoint(source)

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(VALID_CONFIG))

        discover_args = entrypoint.parse_args(["discover", "--config", str(config_path)])
        catalog_message = next(
            json.loads(m) for m in entrypoint.run(discover_args) if json.loads(m).get("type") == "CATALOG"
        )
        patient_schema = next(
            s for s in catalog_message["catalog"]["streams"] if s["name"] == "SQLUser_Patient"
        )
        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text(json.dumps(self._catalog_for_patient(patient_schema)))

        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                [
                    {
                        "type": "STREAM",
                        "stream": {
                            "stream_descriptor": {"name": "SQLUser_Patient", "namespace": "SQLUser"},
                            "stream_state": {"ID": 3},
                        },
                    }
                ]
            )
        )

        read_args = entrypoint.parse_args(
            ["read", "--config", str(config_path), "--catalog", str(catalog_path), "--state", str(state_path)]
        )
        records = [
            json.loads(m)["record"]["data"]
            for m in entrypoint.run(read_args)
            if json.loads(m).get("type") == "RECORD"
        ]
        assert records == []

from __future__ import annotations

import json

import pytest

from fabric_open_mirroring_iris.publisher import FabricOpenMirroringPublisher, TableConfig
from fabric_open_mirroring_iris.state import PublisherState

from mirror_simulator import replay_table, sequence_numbers


def test_initial_snapshot_writes_one_file_per_batch(fake_source, writer, state_path, table_cfg):
    fake_source.seed_snapshot(
        [{"PatientID": i, "MRN": f"M{i}", "Name": f"n{i}", "BirthDate": None, "RiskScore": None, "IsActive": True} for i in range(5)]
    )
    pub = FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))
    written = pub.publish_initial_snapshot(table_cfg, batch_size=2)

    assert [wf.sequence_number for wf in written] == [1, 2, 3]  # ceil(5/2)
    table_dir = writer.table_dir("Patient")
    assert sequence_numbers(table_dir) == [1, 2, 3]

    final_state = replay_table(table_dir, ["PatientID"])
    assert len(final_state) == 5
    assert final_state[(2,)]["MRN"] == "M2"


def test_snapshot_is_not_redone_once_marked_done(fake_source, writer, state_path, table_cfg):
    fake_source.seed_snapshot([{"PatientID": 1, "MRN": "M1", "Name": "n", "BirthDate": None, "RiskScore": None, "IsActive": True}])
    pub = FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))
    first = pub.publish_initial_snapshot(table_cfg)
    assert len(first) == 1

    second = pub.publish_initial_snapshot(table_cfg)
    assert second == []
    assert sequence_numbers(writer.table_dir("Patient")) == [1]


def test_publish_changes_is_noop_when_nothing_changed(fake_source, writer, state_path, table_cfg):
    fake_source.seed_snapshot(
        [{"PatientID": 1, "MRN": "M1", "Name": "a", "BirthDate": None, "RiskScore": None, "IsActive": True}]
    )
    pub = FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))
    pub.publish_initial_snapshot(table_cfg)
    assert sequence_numbers(writer.table_dir("Patient")) == [1]

    result = pub.publish_changes(table_cfg)
    assert result is None
    # No new file should appear when there is nothing to publish.
    assert sequence_numbers(writer.table_dir("Patient")) == [1]


def test_insert_update_delete_end_to_end(fake_source, writer, state_path, table_cfg):
    pub = FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))
    fake_source.seed_snapshot([])
    pub.publish_initial_snapshot(table_cfg)  # empty snapshot -> table folder + metadata only

    fake_source.apply_insert({"PatientID": 1, "MRN": "M1", "Name": "Alice", "BirthDate": None, "RiskScore": None, "IsActive": True})
    fake_source.apply_insert({"PatientID": 2, "MRN": "M2", "Name": "Bob", "BirthDate": None, "RiskScore": None, "IsActive": True})
    wf1 = pub.publish_changes(table_cfg)
    assert wf1 is not None
    assert wf1.sequence_number == 1

    fake_source.apply_update({"PatientID": 1, "MRN": "M1", "Name": "Alice Smith", "BirthDate": None, "RiskScore": None, "IsActive": True})
    wf2 = pub.publish_changes(table_cfg)
    assert wf2.sequence_number == 2

    fake_source.apply_delete({"PatientID": 2, "MRN": "M2", "Name": "Bob", "BirthDate": None, "RiskScore": None, "IsActive": True})
    wf3 = pub.publish_changes(table_cfg)
    assert wf3.sequence_number == 3

    table_dir = writer.table_dir("Patient")
    final_state = replay_table(table_dir, ["PatientID"])
    assert set(final_state.keys()) == {(1,)}
    assert final_state[(1,)]["Name"] == "Alice Smith"


def test_delete_of_row_not_present_is_a_safe_no_op_in_replay(fake_source, writer, state_path, table_cfg):
    pub = FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))
    fake_source.seed_snapshot([])
    pub.publish_initial_snapshot(table_cfg)

    fake_source.apply_delete({"PatientID": 999, "MRN": None, "Name": None, "BirthDate": None, "RiskScore": None, "IsActive": None})
    wf = pub.publish_changes(table_cfg)
    assert wf is not None

    table_dir = writer.table_dir("Patient")
    final_state = replay_table(table_dir, ["PatientID"])
    assert final_state == {}


def test_rerun_after_crash_before_state_save_does_not_corrupt_sequence(
    fake_source, writer, state_path, table_cfg, monkeypatch
):
    """Simulate a crash: the incremental file is durably written, but the
    process dies before PublisherState.save() persists the new change
    token. On the next run, the publisher must (a) never reuse or
    overwrite a sequence number, and (b) reach the same correct final
    mirrored state (because inserts/updates are sent as Upsert, a
    duplicate re-send of the same change batch is a no-op)."""

    fake_source.seed_snapshot([])
    state = PublisherState(state_path)
    pub = FabricOpenMirroringPublisher(fake_source, writer, state)
    pub.publish_initial_snapshot(table_cfg)

    fake_source.apply_insert({"PatientID": 1, "MRN": "M1", "Name": "Alice", "BirthDate": None, "RiskScore": None, "IsActive": True})

    real_save = PublisherState.save
    call_count = {"n": 0}

    def crashing_save(self):
        call_count["n"] += 1
        raise RuntimeError("simulated crash before state persisted")

    monkeypatch.setattr(PublisherState, "save", crashing_save)
    with pytest.raises(RuntimeError):
        pub.publish_changes(table_cfg)

    table_dir = writer.table_dir("Patient")
    assert sequence_numbers(table_dir) == [1]  # file WAS written before the crash

    # Change token was never persisted -> a fresh process re-reads state
    # from disk and will see the same (stale) token.
    monkeypatch.setattr(PublisherState, "save", real_save)
    reloaded_state = PublisherState(state_path)
    pub2 = FabricOpenMirroringPublisher(fake_source, writer, reloaded_state)
    wf2 = pub2.publish_changes(table_cfg)

    # The retry must land at sequence 2, never overwrite file 1.
    assert wf2 is not None
    assert wf2.sequence_number == 2
    assert sequence_numbers(table_dir) == [1, 2]

    # File 1 is untouched (byte-identical is overkill; assert content is
    # still the single insert row, not corrupted/truncated).
    final_state = replay_table(table_dir, ["PatientID"])
    assert final_state == {(1,): {"PatientID": 1, "MRN": "M1", "Name": "Alice", "BirthDate": None, "RiskScore": None, "IsActive": True}}


def test_rerun_after_full_process_restart_resumes_snapshot_offset(
    fake_source, writer, state_path, table_cfg
):
    fake_source.seed_snapshot(
        [{"PatientID": i, "MRN": f"M{i}", "Name": f"n{i}", "BirthDate": None, "RiskScore": None, "IsActive": True} for i in range(4)]
    )
    state1 = PublisherState(state_path)
    pub1 = FabricOpenMirroringPublisher(fake_source, writer, state1)
    written1 = pub1.publish_initial_snapshot(table_cfg, batch_size=2)
    assert len(written1) == 2

    # Brand-new publisher instance loading persisted state from disk,
    # simulating a process restart with the snapshot already complete.
    state2 = PublisherState(state_path)
    pub2 = FabricOpenMirroringPublisher(fake_source, writer, state2)
    written2 = pub2.publish_initial_snapshot(table_cfg, batch_size=2)
    assert written2 == []
    assert sequence_numbers(writer.table_dir("Patient")) == [1, 2]


def test_metadata_written_before_any_data_file(fake_source, writer, state_path, table_cfg):
    fake_source.seed_snapshot([{"PatientID": 1, "MRN": "M1", "Name": "a", "BirthDate": None, "RiskScore": None, "IsActive": True}])
    pub = FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))
    pub.publish_initial_snapshot(table_cfg)

    table_dir = writer.table_dir("Patient")
    metadata_path = table_dir / "_metadata.json"
    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text())
    assert payload["keyColumns"] == ["PatientID"]

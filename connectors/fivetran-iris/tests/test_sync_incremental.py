import pytest

from iris_connector.catalog import describe_table
from iris_connector.fake_db import FakeColumn, FakeConnection, FakeTable
from iris_connector.sync import sync_table_incremental
from tests.helpers import RecordingOperations


def _event_connection():
    table = FakeTable(
        name="EVENT",
        columns=[
            FakeColumn("EVENT_ID", "INTEGER", primary_key=True),
            FakeColumn("UPDATED_AT", "TIMESTAMP"),
            FakeColumn("PAYLOAD", "VARCHAR"),
        ],
        rows=[
            {"EVENT_ID": 1, "UPDATED_AT": "2026-01-01 00:00:00", "PAYLOAD": "a"},
            {"EVENT_ID": 2, "UPDATED_AT": "2026-01-01 00:01:00", "PAYLOAD": "b"},
            {"EVENT_ID": 3, "UPDATED_AT": "2026-01-01 00:02:00", "PAYLOAD": "c"},
            {"EVENT_ID": 4, "UPDATED_AT": "2026-01-01 00:03:00", "PAYLOAD": "d"},
            {"EVENT_ID": 5, "UPDATED_AT": "2026-01-01 00:04:00", "PAYLOAD": "e"},
        ],
    )
    return FakeConnection({"EVENT": table})


def _event_table_columns(conn):
    described = describe_table(conn, "SQLUser", "EVENT")
    assert described is not None
    return described


def test_first_incremental_sync_emits_all_rows_in_cursor_order():
    conn = _event_connection()
    table = _event_table_columns(conn)
    ops = RecordingOperations()
    state = {}

    sync_table_incremental(conn, ops, "SQLUser", table, "UPDATED_AT", state, batch_size=2)

    emitted_ids = [data["EVENT_ID"] for _table, data in ops.upserts]
    assert emitted_ids == [1, 2, 3, 4, 5]
    # Checkpointed after every batch of 2 (3 batches: 2, 2, 1).
    assert len(ops.checkpoints) == 3
    assert state["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:04:00"


def test_second_sync_only_emits_rows_at_or_after_saved_cursor():
    conn = _event_connection()
    table = _event_table_columns(conn)
    ops = RecordingOperations()
    # Simulates state left behind by a prior sync that got through event 3.
    state = {"tables": {"EVENT": {"cursor_value": "2026-01-01 00:02:00"}}}

    sync_table_incremental(conn, ops, "SQLUser", table, "UPDATED_AT", state, batch_size=10)

    emitted_ids = [data["EVENT_ID"] for _table, data in ops.upserts]
    # >= intentionally re-includes the boundary row (event 3): upsert is a
    # keyed overwrite, so re-sending it is a safe no-op, never a duplicate.
    assert emitted_ids == [3, 4, 5]
    assert state["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:04:00"


def test_incremental_sync_advances_cursor_after_every_batch_not_only_at_end():
    conn = _event_connection()
    table = _event_table_columns(conn)
    ops = RecordingOperations()
    state = {}

    sync_table_incremental(conn, ops, "SQLUser", table, "UPDATED_AT", state, batch_size=2)

    # First checkpoint (after the first batch of 2) must already reflect
    # progress through event 2, not wait until the whole table is done.
    assert ops.checkpoints[0]["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:01:00"
    assert ops.checkpoints[1]["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:03:00"
    assert ops.checkpoints[2]["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:04:00"


def test_resume_from_mid_sync_checkpoint_after_simulated_crash_completes_all_rows():
    conn = _event_connection()
    table = _event_table_columns(conn)

    # Run 1: crash after the first checkpoint (2 upserts + 1 checkpoint = 3 ops).
    crashy_ops = RecordingOperations(fail_after=3)
    state = {}
    with pytest.raises(RecordingOperations.SimulatedCrash):
        sync_table_incremental(conn, crashy_ops, "SQLUser", table, "UPDATED_AT", state, batch_size=2)

    assert [data["EVENT_ID"] for _t, data in crashy_ops.upserts] == [1, 2]
    resumed_state = crashy_ops.last_checkpoint
    assert resumed_state["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:01:00"

    # Run 2: resume from exactly the state the last successful checkpoint left.
    conn2 = _event_connection()  # fresh cursor position, same underlying data
    table2 = _event_table_columns(conn2)
    resume_ops = RecordingOperations()
    sync_table_incremental(conn2, resume_ops, "SQLUser", table2, "UPDATED_AT", resumed_state, batch_size=2)

    resumed_ids = [data["EVENT_ID"] for _t, data in resume_ops.upserts]
    # Event 2 is re-sent (>= boundary) then 3, 4, 5 -- union of both runs
    # covers every row, and nothing after event 2 was ever skipped.
    assert resumed_ids == [2, 3, 4, 5]
    all_ids_ever_upserted = {data["EVENT_ID"] for _t, data in crashy_ops.upserts} | set(resumed_ids)
    assert all_ids_ever_upserted == {1, 2, 3, 4, 5}
    assert resumed_state["tables"]["EVENT"]["cursor_value"] == "2026-01-01 00:04:00"


def test_invalid_cursor_field_skips_table_and_warns():
    conn = _event_connection()
    table = _event_table_columns(conn)
    ops = RecordingOperations()
    state = {}
    warnings = []

    sync_table_incremental(
        conn, ops, "SQLUser", table, "NOT_A_COLUMN", state, batch_size=10, warn=warnings.append
    )

    assert ops.upserts == []
    assert ops.checkpoints == []
    assert any("NOT_A_COLUMN" in w for w in warnings)

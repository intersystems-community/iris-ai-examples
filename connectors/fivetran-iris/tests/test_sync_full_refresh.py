import pytest

from iris_connector.catalog import describe_table
from iris_connector.fake_db import FakeColumn, FakeConnection, FakeTable
from iris_connector.sync import sync_table_full_refresh
from tests.helpers import RecordingOperations


def _product_connection():
    table = FakeTable(
        name="PRODUCT",
        columns=[
            FakeColumn("PRODUCT_ID", "INTEGER", primary_key=True),
            FakeColumn("NAME", "VARCHAR"),
        ],
        rows=[{"PRODUCT_ID": i, "NAME": f"widget-{i}"} for i in range(1, 6)],
    )
    return FakeConnection({"PRODUCT": table})


def _lookup_connection():
    """A table with NO primary key -- exercises the non-resumable fallback."""
    table = FakeTable(
        name="LOOKUP",
        columns=[FakeColumn("CODE", "VARCHAR"), FakeColumn("LABEL", "VARCHAR")],
        rows=[{"CODE": "A", "LABEL": "alpha"}, {"CODE": "B", "LABEL": "beta"}],
    )
    return FakeConnection({"LOOKUP": table})


def test_full_refresh_truncates_once_and_upserts_all_rows():
    conn = _product_connection()
    table = describe_table(conn, "SQLUser", "PRODUCT")
    ops = RecordingOperations()
    state = {}

    sync_table_full_refresh(conn, ops, "SQLUser", table, state, batch_size=2)

    assert ops.truncates == ["PRODUCT"]
    emitted_ids = [data["PRODUCT_ID"] for _t, data in ops.upserts]
    assert emitted_ids == [1, 2, 3, 4, 5]


def test_full_refresh_resets_state_to_fresh_shape_when_done():
    conn = _product_connection()
    table = describe_table(conn, "SQLUser", "PRODUCT")
    ops = RecordingOperations()
    state = {}

    sync_table_full_refresh(conn, ops, "SQLUser", table, state, batch_size=2)

    assert state["tables"]["PRODUCT"] == {"truncated": False, "resume_after_pk": None}


def test_full_refresh_checkpoints_truncate_before_any_upserts():
    conn = _product_connection()
    table = describe_table(conn, "SQLUser", "PRODUCT")
    ops = RecordingOperations()
    state = {}

    sync_table_full_refresh(conn, ops, "SQLUser", table, state, batch_size=2)

    # First recorded checkpoint must be the truncate-acknowledgment
    # checkpoint, taken before any row data was upserted.
    first_checkpoint = ops.checkpoints[0]
    assert first_checkpoint["tables"]["PRODUCT"]["truncated"] is True
    assert first_checkpoint["tables"]["PRODUCT"]["resume_after_pk"] is None


def test_resume_after_crash_mid_load_does_not_retruncate_and_completes():
    conn = _product_connection()
    table = describe_table(conn, "SQLUser", "PRODUCT")

    # Run 1: crash right after the second batch's checkpoint.
    # Ops sequence: truncate(1), checkpoint(2) [truncate-ack],
    # upsert x2 (3,4), checkpoint(5) [batch 1: rows 1-2],
    # upsert x2 (6,7), checkpoint(8) [batch 2: rows 3-4] -> crash here.
    crashy_ops = RecordingOperations(fail_after=8)
    state = {}
    with pytest.raises(RecordingOperations.SimulatedCrash):
        sync_table_full_refresh(conn, crashy_ops, "SQLUser", table, state, batch_size=2)

    assert crashy_ops.truncates == ["PRODUCT"]
    assert [data["PRODUCT_ID"] for _t, data in crashy_ops.upserts] == [1, 2, 3, 4]
    resumed_state = crashy_ops.last_checkpoint
    assert resumed_state["tables"]["PRODUCT"]["truncated"] is True
    assert resumed_state["tables"]["PRODUCT"]["resume_after_pk"] == 4

    # Run 2: resume. Must NOT truncate again, and must pick up from pk > 4.
    conn2 = _product_connection()
    table2 = describe_table(conn2, "SQLUser", "PRODUCT")
    resume_ops = RecordingOperations()
    sync_table_full_refresh(conn2, resume_ops, "SQLUser", table2, resumed_state, batch_size=2)

    assert resume_ops.truncates == []  # not re-truncated
    assert [data["PRODUCT_ID"] for _t, data in resume_ops.upserts] == [5]
    # Cycle complete: state resets to the fresh shape for next time.
    assert resumed_state["tables"]["PRODUCT"] == {"truncated": False, "resume_after_pk": None}

    all_ids = {data["PRODUCT_ID"] for _t, data in crashy_ops.upserts} | {
        data["PRODUCT_ID"] for _t, data in resume_ops.upserts
    }
    assert all_ids == {1, 2, 3, 4, 5}


def test_full_refresh_without_primary_key_still_truncates_once_and_loads_all_rows():
    conn = _lookup_connection()
    table = describe_table(conn, "SQLUser", "LOOKUP")
    assert table.primary_key == []  # no PK -> non-resumable fallback path
    ops = RecordingOperations()
    state = {}

    sync_table_full_refresh(conn, ops, "SQLUser", table, state, batch_size=10)

    assert ops.truncates == ["LOOKUP"]
    emitted_codes = {data["CODE"] for _t, data in ops.upserts}
    assert emitted_codes == {"A", "B"}
    assert state["tables"]["LOOKUP"] == {"truncated": False, "resume_after_pk": None}

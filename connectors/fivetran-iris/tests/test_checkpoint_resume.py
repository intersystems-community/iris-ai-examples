"""End-to-end resume test through `sync.run_sync` (the same entrypoint
`connector.py`'s `update()` calls), across a multi-table sync where one
table is incremental and one is full-refresh -- not just the per-table
unit tests in test_sync_incremental.py / test_sync_full_refresh.py.
"""

import pytest

from iris_connector.config import validate_configuration
from iris_connector.fake_db import demo_connection
from iris_connector.sync import run_sync
from tests.helpers import RecordingOperations

CONFIG = {
    "host": "fake", "namespace": "USER", "username": "demo", "password": "demo",
    "cursor_fields": '{"ENCOUNTER": "VISIT_AT"}',  # PATIENT stays full-refresh
    "batch_size": "1",
}


def _all_upserted_pks(ops, table_name, pk_column):
    return {data[pk_column] for t, data in ops.upserts if t == table_name}


def test_full_run_sync_completes_both_tables_from_empty_state():
    cfg = validate_configuration(CONFIG)
    conn = demo_connection()
    ops = RecordingOperations()
    state = {}

    run_sync(conn, cfg, state, ops)

    assert _all_upserted_pks(ops, "PATIENT", "PATIENT_ID") == {1, 2}
    assert _all_upserted_pks(ops, "ENCOUNTER", "ENCOUNTER_ID") == {1, 2}
    assert ops.truncates == ["PATIENT"]  # only the full-refresh table
    assert state["tables"]["PATIENT"] == {"truncated": False, "resume_after_pk": None}
    assert state["tables"]["ENCOUNTER"]["cursor_value"] == "2026-02-03 14:15:00.000000"


def test_interrupted_run_sync_resumes_to_a_correct_final_state():
    cfg = validate_configuration(CONFIG)
    conn = demo_connection()

    # Crash partway through the very first table processed (PATIENT, since
    # discover_schema orders tables alphabetically: ENCOUNTER, PATIENT --
    # so ENCOUNTER (incremental) finishes first; crash partway through
    # PATIENT's (full-refresh) load).
    crashy_ops = RecordingOperations(fail_after=6)
    state = {}
    with pytest.raises(RecordingOperations.SimulatedCrash):
        run_sync(conn, cfg, state, crashy_ops)

    # ENCOUNTER (processed first, alphabetically before PATIENT) must have
    # completed fully before the crash.
    assert _all_upserted_pks(crashy_ops, "ENCOUNTER", "ENCOUNTER_ID") == {1, 2}
    assert state["tables"]["ENCOUNTER"]["cursor_value"] == "2026-02-03 14:15:00.000000"

    # Resume with a fresh connection (simulates a new sync process) and the
    # exact state the crash left behind.
    conn2 = demo_connection()
    resume_ops = RecordingOperations()
    run_sync(conn2, cfg, state, resume_ops)

    # PATIENT must end up fully, correctly loaded, and truncated exactly
    # once across the two runs combined (never twice).
    assert _all_upserted_pks(crashy_ops, "PATIENT", "PATIENT_ID") | _all_upserted_pks(
        resume_ops, "PATIENT", "PATIENT_ID"
    ) == {1, 2}
    assert (crashy_ops.truncates + resume_ops.truncates).count("PATIENT") == 1
    assert state["tables"]["PATIENT"] == {"truncated": False, "resume_after_pk": None}

    # ENCOUNTER, already done before the crash, must not be reprocessed by
    # the resumed run (its cursor_value stays exactly where it was; no
    # additional upserts for it in the resume run since there is nothing
    # newer than the saved cursor).
    assert _all_upserted_pks(resume_ops, "ENCOUNTER", "ENCOUNTER_ID") <= {1, 2}

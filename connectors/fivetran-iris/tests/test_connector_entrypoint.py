"""Exercises `connector.py` itself -- the actual Fivetran entrypoint file,
not just `iris_connector/` -- for the parts that are safe to call directly
in a plain `pytest` process.

`schema()` is pure read-plus-return and is fully covered here. `update()`
is NOT called through `connector.py` in this file: it calls the real
`fivetran_connector_sdk.Operations.checkpoint()`, which blocks waiting for
the SDK's own gRPC consumer loop to drain its internal queue -- a loop that
only exists when running under `fivetran debug`/`deploy`. That path is
exercised for real in the `fivetran debug` run documented in STATUS.md;
`iris_connector.sync.run_sync()` (covered by test_sync_*.py and
test_checkpoint_resume.py) is the same code `update()` calls, driven
through the `SyncOperations` interface instead.

Skipped entirely if `fivetran_connector_sdk` is not installed, so the rest
of the suite stays runnable with zero network access and zero extra
dependencies -- this file is the only one that needs the real SDK.
"""

import pytest

pytest.importorskip("fivetran_connector_sdk")

import connector  # noqa: E402  (import after importorskip, by design)
from fivetran_connector_sdk import Logging  # noqa: E402
from iris_connector.config import ConfigurationError  # noqa: E402
from iris_connector.fake_db import FakeConnection  # noqa: E402

# `Logging.LOG_LEVEL` starts as None and is normally set by the `fivetran
# debug`/`deploy` CLI harness before it ever calls into connector code;
# calling Logging.info/warning without it set raises TypeError (discovered
# by running this test against the real SDK). Set the same default the CLI
# uses (`connector_helper.py`'s own fallback is `Logging.Level.INFO`) so
# connector.py's calls to `Logging.warning` behave the same here as they do
# under `fivetran debug`.
Logging.LOG_LEVEL = Logging.Level.INFO

FAKE_CONFIG = {
    "host": "fake", "namespace": "USER", "username": "demo", "password": "demo",
    "driver": "fake",
}


def test_connect_with_driver_fake_returns_fake_connection():
    cfg = connector.validate_configuration(FAKE_CONFIG)
    conn = connector._connect(FAKE_CONFIG, cfg)
    try:
        assert isinstance(conn, FakeConnection)
    finally:
        conn.close()


def test_schema_against_fake_driver_matches_catalog_output():
    schema_defs = connector.schema(FAKE_CONFIG)
    by_name = {entry["table"]: entry for entry in schema_defs}
    assert set(by_name) == {"PATIENT", "ENCOUNTER"}
    assert by_name["PATIENT"]["primary_key"] == ["PATIENT_ID"]
    assert "CHART_NOTE" not in by_name["PATIENT"]["columns"]  # LONGVARCHAR dropped


def test_schema_propagates_configuration_errors_before_connecting():
    with pytest.raises(ConfigurationError):
        connector.schema({})


def test_update_propagates_configuration_errors_before_connecting():
    with pytest.raises(ConfigurationError):
        connector.update({}, {})

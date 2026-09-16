import logging

from source_iris.source import IrisSource

from .conftest import VALID_CONFIG

logger = logging.getLogger("test")


class TestCheckConnection:
    def test_success(self, connection_factory):
        source = IrisSource(connection_factory=connection_factory)
        ok, error = source.check_connection(logger, VALID_CONFIG)
        assert ok is True
        assert error is None

    def test_failure_when_query_fails(self, sample_tables_catalog, sample_columns_catalog, sample_table_data):
        from .fakes import FakeIrisConnection

        conn = FakeIrisConnection(
            tables_catalog=sample_tables_catalog,
            columns_catalog=sample_columns_catalog,
            table_data=sample_table_data,
            fail_test_query=True,
        )
        source = IrisSource(connection_factory=lambda config: conn)
        ok, error = source.check_connection(logger, VALID_CONFIG)
        assert ok is False
        assert error is not None
        assert "simulated IRIS connectivity failure" in error

    def test_failure_when_connection_cannot_be_established(self):
        def failing_factory(config):
            raise ConnectionError("could not reach host")

        source = IrisSource(connection_factory=failing_factory)
        ok, error = source.check_connection(logger, VALID_CONFIG)
        assert ok is False
        assert "could not reach host" in error

    def test_check_via_airbyte_protocol_message(self, connection_factory):
        # Exercise AbstractSource.check() (not just check_connection()) so we assert on
        # the actual AirbyteConnectionStatus protocol object the platform receives.
        from airbyte_cdk.models import Status

        source = IrisSource(connection_factory=connection_factory)
        status = source.check(logger, VALID_CONFIG)
        assert status.status == Status.SUCCEEDED

    def test_check_failure_via_airbyte_protocol_message(self):
        from airbyte_cdk.models import Status

        def failing_factory(config):
            raise ConnectionError("nope")

        source = IrisSource(connection_factory=failing_factory)
        status = source.check(logger, VALID_CONFIG)
        assert status.status == Status.FAILED

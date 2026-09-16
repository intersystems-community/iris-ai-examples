import sys
import types

from source_iris.db import DBAPIConnection, DBAPICursor, connect_real_iris

from .fakes import FakeIrisConnection


class TestFakeSatisfiesProtocol:
    def test_fake_connection_satisfies_dbapi_connection_protocol(self, fake_connection):
        assert isinstance(fake_connection, DBAPIConnection)

    def test_fake_cursor_satisfies_dbapi_cursor_protocol(self, fake_connection):
        cursor = fake_connection.cursor()
        assert isinstance(cursor, DBAPICursor)


class TestConnectRealIris:
    def test_builds_expected_dbapi_connect_kwargs(self, monkeypatch):
        # Stub out `iris.dbapi` entirely so this test needs no live IRIS/Docker, while
        # still proving connect_real_iris maps the Airbyte config dict onto the exact
        # keyword arguments documented for iris.dbapi.connect (hostname, port,
        # namespace, username, password, timeout). See db.py's docstring for the
        # docs.intersystems.com reference.
        captured = {}

        def fake_connect(**kwargs):
            captured.update(kwargs)
            return FakeIrisConnection()

        fake_iris_dbapi_module = types.SimpleNamespace(connect=fake_connect)
        fake_iris_module = types.SimpleNamespace(dbapi=fake_iris_dbapi_module)
        monkeypatch.setitem(sys.modules, "iris", fake_iris_module)
        monkeypatch.setitem(sys.modules, "iris.dbapi", fake_iris_dbapi_module)

        config = {
            "host": "iris.example.com",
            "port": 51972,
            "namespace": "DEMO",
            "username": "demo_user",
            "password": "demo_pass",
            "connection_timeout_seconds": 5,
        }
        connect_real_iris(config)

        assert captured == {
            "hostname": "iris.example.com",
            "port": 51972,
            "namespace": "DEMO",
            "username": "demo_user",
            "password": "demo_pass",
            "timeout": 5,
        }

    def test_defaults_port_namespace_and_timeout(self, monkeypatch):
        captured = {}

        def fake_connect(**kwargs):
            captured.update(kwargs)
            return FakeIrisConnection()

        fake_iris_dbapi_module = types.SimpleNamespace(connect=fake_connect)
        fake_iris_module = types.SimpleNamespace(dbapi=fake_iris_dbapi_module)
        monkeypatch.setitem(sys.modules, "iris", fake_iris_module)
        monkeypatch.setitem(sys.modules, "iris.dbapi", fake_iris_dbapi_module)

        connect_real_iris({"host": "h", "username": "u", "password": "p"})

        assert captured["port"] == 1972
        assert captured["namespace"] == "USER"
        assert captured["timeout"] == 20

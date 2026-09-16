import sys

import pytest

from iris_connector import db
from iris_connector.config import validate_configuration


def test_connect_raises_clear_runtime_error_when_iris_package_missing(monkeypatch):
    # Setting sys.modules["iris"] = None makes `import iris` raise
    # ImportError, simulating an environment without
    # `intersystems-irispython` installed -- without needing to actually
    # uninstall it.
    monkeypatch.setitem(sys.modules, "iris", None)

    cfg = validate_configuration(
        {"host": "h", "namespace": "USER", "username": "u", "password": "p"}
    )
    with pytest.raises(RuntimeError, match="intersystems-irispython"):
        db.connect(cfg)


def test_fake_connection_satisfies_the_dbconnection_protocol():
    from iris_connector.fake_db import demo_connection

    conn = demo_connection()
    assert isinstance(conn, db.DBConnection)
    cursor = conn.cursor()
    assert isinstance(cursor, db.DBCursor)
    cursor.close()
    conn.close()

from __future__ import annotations

import pytest

from .fakes import FakeIrisConnection

VALID_CONFIG = {
    "host": "localhost",
    "port": 1972,
    "namespace": "USER",
    "username": "_SYSTEM",
    "password": "SYS",
    "connection_timeout_seconds": 20,
}


@pytest.fixture
def sample_tables_catalog():
    return [
        ("SQLUser", "Patient", "BASE TABLE"),
        ("SQLUser", "Note", "BASE TABLE"),
        # A system schema table that must never surface from default discovery.
        ("%SYS", "Config", "BASE TABLE"),
    ]


@pytest.fixture
def sample_columns_catalog():
    return {
        ("SQLUser", "Patient"): [
            # (COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION, PRIMARY_KEY,
            #  NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH)
            ("ID", "BIGINT", "NO", 1, "YES", 19, 0, None),
            ("NAME", "VARCHAR", "YES", 2, "NO", None, None, 100),
            ("UPDATED_AT", "TIMESTAMP", "YES", 3, "NO", None, None, None),
            ("NOTES", "LONGVARCHAR", "YES", 4, "NO", None, None, None),
        ],
        ("SQLUser", "Note"): [
            # No primary key at all -> full-refresh only.
            ("NOTE_ID", "INTEGER", "NO", 1, "NO", 10, 0, None),
            ("BODY", "VARCHAR", "YES", 2, "NO", None, None, 4000),
        ],
    }


@pytest.fixture
def sample_table_data():
    return {
        ("SQLUser", "Patient"): [
            {"ID": 1, "NAME": "Ada Lovelace", "UPDATED_AT": "2026-01-01 00:00:00.000000", "NOTES": "n1"},
            {"ID": 2, "NAME": "Grace Hopper", "UPDATED_AT": "2026-01-02 00:00:00.000000", "NOTES": "n2"},
            {"ID": 3, "NAME": "Ada Yonath", "UPDATED_AT": "2026-01-03 00:00:00.000000", "NOTES": "n3"},
        ],
        ("SQLUser", "Note"): [
            {"NOTE_ID": 10, "BODY": "first"},
            {"NOTE_ID": 11, "BODY": "second"},
        ],
    }


@pytest.fixture
def fake_connection(sample_tables_catalog, sample_columns_catalog, sample_table_data):
    return FakeIrisConnection(
        tables_catalog=sample_tables_catalog,
        columns_catalog=sample_columns_catalog,
        table_data=sample_table_data,
    )


@pytest.fixture
def connection_factory(fake_connection):
    """A ConnectionFactory (see source_iris.source) that always returns the same fake connection."""

    def factory(config):
        return fake_connection

    return factory

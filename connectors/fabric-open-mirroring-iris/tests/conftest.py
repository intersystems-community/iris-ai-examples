from __future__ import annotations

import pytest

from fabric_open_mirroring_iris.iris_types import ColumnDef
from fabric_open_mirroring_iris.landing_zone import OpenMirroringLandingZoneWriter
from fabric_open_mirroring_iris.publisher import FabricOpenMirroringPublisher, TableConfig
from fabric_open_mirroring_iris.source import FakeIrisSource
from fabric_open_mirroring_iris.state import PublisherState

PATIENT_SCHEMA = [
    ColumnDef("PatientID", "BIGINT", nullable=False),
    ColumnDef("MRN", "VARCHAR", nullable=False, max_length=32),
    ColumnDef("Name", "VARCHAR", nullable=True, max_length=200),
    ColumnDef("BirthDate", "DATE", nullable=True),
    ColumnDef("RiskScore", "NUMERIC", nullable=True, precision=10, scale=2),
    ColumnDef("IsActive", "BIT", nullable=True),
]

KEY_COLUMNS = ["PatientID"]


@pytest.fixture
def landing_zone_root(tmp_path):
    return tmp_path / "mirrored-db" / "Files" / "LandingZone"


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "_publisher_state" / "state.json"


@pytest.fixture
def fake_source():
    return FakeIrisSource(schema=list(PATIENT_SCHEMA), key_columns=KEY_COLUMNS)


@pytest.fixture
def writer(landing_zone_root):
    return OpenMirroringLandingZoneWriter(landing_zone_root)


@pytest.fixture
def table_cfg():
    return TableConfig(table_name="Patient", key_columns=KEY_COLUMNS)


def make_publisher(fake_source, writer, state_path):
    return FabricOpenMirroringPublisher(fake_source, writer, PublisherState(state_path))


@pytest.fixture
def publisher(fake_source, writer, state_path):
    return make_publisher(fake_source, writer, state_path)

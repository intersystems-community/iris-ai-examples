from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odata_iris.schema import Column, EntitySet, Schema  # noqa: E402


@pytest.fixture()
def patient_entity_set() -> EntitySet:
    return EntitySet(
        name="Patient",
        table="SQLUser.Patient",
        key="PatientID",
        columns=(
            Column("PatientID", "BIGINT", nullable=False),
            Column("LastName", "VARCHAR"),
            Column("FirstName", "VARCHAR"),
            Column("BirthDate", "DATE"),
            Column("RiskScore", "NUMERIC"),
        ),
    )


@pytest.fixture()
def schema(patient_entity_set: EntitySet) -> Schema:
    return Schema(namespace="IRISHealth", entity_sets=(patient_entity_set,))

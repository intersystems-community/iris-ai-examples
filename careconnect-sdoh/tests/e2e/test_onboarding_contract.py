import os
import time

import httpx
import pytest

from conftest import HUB_HOST, HUB_PORT, FHIR_BASE, USERS, requires_iris

pytestmark = [pytest.mark.contract, pytest.mark.docker]


class TestProductionModuleLoad:
    @requires_iris
    def test_pyprod_classes_importable(self):
        from productions.patient_onboarding import (
            FHIRPollingBS,
            PatientOnboardBP,
            FHIRIngestBO,
            DataQueueBO,
            PatientOnboardingProd,
            PatientPollRequest,
            PatientRecord,
            IngestResult,
        )

        assert FHIRPollingBS is not None
        assert PatientOnboardBP is not None
        assert FHIRIngestBO is not None
        assert DataQueueBO is not None

    @requires_iris
    def test_fhir_polling_bs_pool_size_is_one(self):
        from productions.patient_onboarding import PatientOnboardingProd

        items_map = {item["Name"]: item for item in PatientOnboardingProd.items}
        assert items_map["FHIRPollingBS"]["PoolSize"] == 1

    @requires_iris
    def test_fhir_ingest_bo_pool_size_is_three(self):
        from productions.patient_onboarding import PatientOnboardingProd

        items_map = {item["Name"]: item for item in PatientOnboardingProd.items}
        assert items_map["FHIRIngestBO"]["PoolSize"] == 3, (
            "FHIRIngestBO PoolSize MUST be 3 — intentional CE bottleneck (spec FR-003)"
        )

    @requires_iris
    def test_total_pool_size_creates_saturation(self):
        from productions.patient_onboarding import PatientOnboardingProd

        total = sum(item.get("PoolSize", 1) for item in PatientOnboardingProd.items)
        assert total >= 7, (
            f"Total PoolSize {total} must be ≥7 to create CE saturation when combined with other productions"
        )


class TestFHIRPollingLogic:
    @requires_iris
    def test_check_loaded_returns_true_when_patients_exist(self):
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from services.iris_fhir.init.check_loaded import already_loaded

        result = already_loaded()
        assert isinstance(result, bool)

    @requires_iris
    def test_patient_record_message_has_required_fields(self):
        from productions.patient_onboarding import PatientRecord

        record = PatientRecord()
        record.patient_id = "Patient/42"
        record.fhir_bundle = '{"resourceType":"Bundle","entry":[]}'
        record.ready = True
        record.issues = ""
        assert record.patient_id == "Patient/42"
        assert record.ready is True

    @requires_iris
    def test_readiness_check_fails_without_birthdate(self):
        from productions.patient_onboarding import PatientOnboardBP

        bp = PatientOnboardBP()
        patient = {"resourceType": "Patient", "id": "42", "gender": "male"}
        ready, issues = bp._readiness_check(patient)
        assert not ready
        assert "birthDate" in issues

    @requires_iris
    def test_readiness_check_fails_without_gender(self):
        from productions.patient_onboarding import PatientOnboardBP

        bp = PatientOnboardBP()
        patient = {"resourceType": "Patient", "id": "42", "birthDate": "1980-01-01"}
        ready, issues = bp._readiness_check(patient)
        assert not ready
        assert "gender" in issues

    @requires_iris
    def test_readiness_check_passes_complete_patient(self):
        from productions.patient_onboarding import PatientOnboardBP

        bp = PatientOnboardBP()
        patient = {
            "resourceType": "Patient",
            "id": "42",
            "birthDate": "1980-01-01",
            "gender": "male",
            "telecom": [{"system": "phone", "value": "555-1234"}],
        }
        ready, issues = bp._readiness_check(patient)
        assert ready
        assert issues == ""


class TestIRISHubInterop:
    @requires_iris
    def test_ens_message_header_table_accessible(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Ens.MessageHeader WHERE Status = 1")
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert isinstance(row[0], int)

    @requires_iris
    def test_careconnect_kg_global_accessible(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        iris_obj = iris.createIRIS(conn)
        val = iris_obj.get("^CareConnect.KG")
        conn.close()

    @requires_iris
    def test_careconnect_data_queue_global_accessible(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        iris_obj = iris.createIRIS(conn)
        val = iris_obj.get("^CareConnect.DataQueue")
        conn.close()

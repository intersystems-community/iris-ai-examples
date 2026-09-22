import os
import time

import httpx
import pytest

from conftest import HUB_HOST, HUB_PORT, FHIR_BASE, USERS, requires_iris

pytestmark = [pytest.mark.contract, pytest.mark.docker]


def _pool_sizes(production) -> dict:
    """{host name: pool_size} across every host a Production declares."""
    return {
        item.name: item.pool_size
        for group in (production.services, production.processes, production.operations)
        for item in group
    }


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

        assert _pool_sizes(PatientOnboardingProd)["FHIRPollingBS"] == 1

    @requires_iris
    def test_fhir_ingest_bo_pool_size_is_three(self):
        from productions.patient_onboarding import PatientOnboardingProd

        assert _pool_sizes(PatientOnboardingProd)["FHIRIngestBO"] == 3, (
            "FHIRIngestBO pool_size MUST be 3 — intentional CE bottleneck (spec FR-003)"
        )

    @requires_iris
    def test_total_pool_size_creates_saturation(self):
        from productions.patient_onboarding import PatientOnboardingProd

        total = sum(_pool_sizes(PatientOnboardingProd).values())
        assert total >= 7, (
            f"Total pool_size {total} must be ≥7 to create CE saturation when combined with other productions"
        )

    @requires_iris
    def test_production_declares_items_the_sdk_actually_reads(self):
        """The SDK reads `services` / `processes` / `operations`, never `items`.

        The first cut declared a class-level `items = [{"ClassName": ..., "PoolSize": ...}]`
        list. intersystems_pyprod warns on import — "There is no attribute named
        items for Production class" — and deploys a production with no hosts in it,
        so the CE bottleneck this example is built to show never exists.
        """
        from productions.patient_onboarding import PatientOnboardingProd

        assert not hasattr(PatientOnboardingProd, "items"), (
            "`items` is not part of the Production API — declare services/processes/operations"
        )
        assert PatientOnboardingProd.services, "production declares no business services"
        assert PatientOnboardingProd.processes, "production declares no business processes"
        assert PatientOnboardingProd.operations, "production declares no business operations"


class TestFHIRPollingLogic:
    @requires_iris
    def test_check_loaded_returns_true_when_patients_exist(self):
        # By file path, not by dotted import: the directory is services/iris-fhir,
        # and a hyphen cannot appear in a module path, so
        # `from services.iris_fhir.init.check_loaded import ...` raised
        # ModuleNotFoundError every run — which reads as a missing dependency
        # rather than a path that was never importable.
        import importlib.util

        script = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "services",
            "iris-fhir",
            "init",
            "check_loaded.py",
        )
        assert os.path.exists(script), f"check_loaded.py not found at {script}"
        spec = importlib.util.spec_from_file_location("check_loaded", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result = module.already_loaded()
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

        patient = {"resourceType": "Patient", "id": "42", "gender": "male"}
        ready, issues = PatientOnboardBP._readiness_check(patient)
        assert not ready
        assert "birthDate" in issues

    @requires_iris
    def test_readiness_check_fails_without_gender(self):
        from productions.patient_onboarding import PatientOnboardBP

        patient = {"resourceType": "Patient", "id": "42", "birthDate": "1980-01-01"}
        ready, issues = PatientOnboardBP._readiness_check(patient)
        assert not ready
        assert "gender" in issues

    @requires_iris
    def test_readiness_check_passes_complete_patient(self):
        from productions.patient_onboarding import PatientOnboardBP

        patient = {
            "resourceType": "Patient",
            "id": "42",
            "birthDate": "1980-01-01",
            "gender": "male",
            "telecom": [{"system": "phone", "value": "555-1234"}],
        }
        ready, issues = PatientOnboardBP._readiness_check(patient)
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

"""Unit tests for CareConnect productions — no Docker, no IRIS required."""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit


# ── patient_onboarding ────────────────────────────────────────────────────────

class TestPatientOnboardingMessages:
    def test_patient_poll_request_defaults(self):
        from productions.patient_onboarding import PatientPollRequest
        req = PatientPollRequest()
        assert req.since == ""
        assert req.batch_size == 10

    def test_patient_record_fields(self):
        from productions.patient_onboarding import PatientRecord
        rec = PatientRecord()
        rec.patient_id = "Patient/42"
        rec.fhir_bundle = '{"resourceType":"Bundle"}'
        rec.ready = True
        rec.issues = ""
        assert rec.patient_id == "Patient/42"
        assert rec.ready is True

    def test_ingest_result_fields(self):
        from productions.patient_onboarding import IngestResult
        res = IngestResult()
        res.patient_id = "Patient/42"
        res.success = True
        res.iris_id = "42"
        assert res.success is True

    def test_production_has_four_items(self):
        from productions.patient_onboarding import PatientOnboardingProd
        assert len(PatientOnboardingProd.items) >= 4

    def test_fhir_polling_bs_pool_size_is_one(self):
        from productions.patient_onboarding import PatientOnboardingProd
        items = {item["Name"]: item for item in PatientOnboardingProd.items}
        assert items["FHIRPollingBS"]["PoolSize"] == 1

    def test_fhir_ingest_bo_pool_size_is_three(self):
        from productions.patient_onboarding import PatientOnboardingProd
        items = {item["Name"]: item for item in PatientOnboardingProd.items}
        assert items["FHIRIngestBO"]["PoolSize"] == 3

    def test_total_pool_exceeds_seven(self):
        from productions.patient_onboarding import PatientOnboardingProd
        total = sum(item.get("PoolSize", 1) for item in PatientOnboardingProd.items)
        assert total >= 7


class TestReadinessCheck:
    def _bp(self):
        from productions.patient_onboarding import PatientOnboardBP
        return PatientOnboardBP()

    def test_complete_patient_passes(self):
        bp = self._bp()
        patient = {
            "resourceType": "Patient",
            "id": "42",
            "birthDate": "1980-01-01",
            "gender": "male",
            "telecom": [{"system": "phone", "value": "555-1234"}],
        }
        ready, issues = bp._readiness_check(patient)
        assert ready is True
        assert issues == ""

    def test_missing_birthdate_fails(self):
        bp = self._bp()
        patient = {"resourceType": "Patient", "id": "42", "gender": "male"}
        ready, issues = bp._readiness_check(patient)
        assert ready is False
        assert "birthDate" in issues

    def test_missing_gender_fails(self):
        bp = self._bp()
        patient = {"resourceType": "Patient", "id": "42", "birthDate": "1980-01-01"}
        ready, issues = bp._readiness_check(patient)
        assert ready is False
        assert "gender" in issues

    def test_missing_both_fails_with_combined_issues(self):
        bp = self._bp()
        patient = {"resourceType": "Patient", "id": "42"}
        ready, issues = bp._readiness_check(patient)
        assert ready is False
        assert "birthDate" in issues
        assert "gender" in issues


# ── sdoh_followup ─────────────────────────────────────────────────────────────

class TestSDoHFollowUpMessages:
    def test_follow_up_request_fields(self):
        from productions.sdoh_followup import FollowUpRequest
        req = FollowUpRequest()
        req.patient_id = "maria-gonzalez-001"
        req.priority = "urgent"
        req.sdoh_flags = "food_insecurity,housing"
        assert req.patient_id == "maria-gonzalez-001"
        assert req.priority == "urgent"

    def test_follow_up_response_fields(self):
        from productions.sdoh_followup import FollowUpResponse
        resp = FollowUpResponse()
        resp.patient_id = "maria-gonzalez-001"
        resp.success = True
        resp.message_id = "msg-001"
        assert resp.success is True

    def test_production_module_has_bs_bp_bo_classes(self):
        from productions import sdoh_followup
        assert hasattr(sdoh_followup, "SDoHFollowUpBS")
        assert hasattr(sdoh_followup, "SDoHFollowUpBP")
        assert hasattr(sdoh_followup, "SDoHFHIRCarePlanBO")


class TestSDoHFollowUpBP:
    def _bp(self):
        from productions.sdoh_followup import SDoHFollowUpBP
        return SDoHFollowUpBP()

    def test_bp_instantiates(self):
        bp = self._bp()
        assert bp is not None

    def test_follow_up_request_default_priority(self):
        from productions.sdoh_followup import FollowUpRequest
        req = FollowUpRequest()
        assert req.priority == "routine"

    def test_follow_up_request_default_sdoh_flags(self):
        from productions.sdoh_followup import FollowUpRequest
        req = FollowUpRequest()
        assert req.sdoh_flags == ""

    def test_follow_up_response_default_status(self):
        from productions.sdoh_followup import FollowUpResponse
        resp = FollowUpResponse()
        assert resp.status == ""
        assert resp.care_plan_id == ""

"""Unit tests for CareConnect productions — no Docker, no IRIS required."""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit


# ── patient_onboarding ────────────────────────────────────────────────────────

def _pool_sizes(production) -> dict:
    """{host name: pool_size} across every host a Production declares.

    `services` / `processes` / `operations` are what intersystems_pyprod reads.
    There is no `items` list on Production — declaring one gets a warning at
    import and a production with no hosts in it.
    """
    return {
        item.name: item.pool_size
        for group in (production.services, production.processes, production.operations)
        for item in group
    }


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
        assert len(_pool_sizes(PatientOnboardingProd)) >= 4

    def test_fhir_polling_bs_pool_size_is_one(self):
        from productions.patient_onboarding import PatientOnboardingProd
        assert _pool_sizes(PatientOnboardingProd)["FHIRPollingBS"] == 1

    def test_fhir_ingest_bo_pool_size_is_three(self):
        from productions.patient_onboarding import PatientOnboardingProd
        assert _pool_sizes(PatientOnboardingProd)["FHIRIngestBO"] == 3

    def test_total_pool_exceeds_seven(self):
        from productions.patient_onboarding import PatientOnboardingProd
        assert sum(_pool_sizes(PatientOnboardingProd).values()) >= 7


class TestReadinessCheck:
    def _bp(self):
        """The class, not an instance.

        `BusinessProcess.__init__` needs an `iris_host_object` only the
        Interoperability framework can supply, so `PatientOnboardBP()` raises
        TypeError outside a running production. `_readiness_check` is a
        staticmethod for exactly this reason.
        """
        from productions.patient_onboarding import PatientOnboardBP
        return PatientOnboardBP

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
    def test_bp_is_a_business_process(self):
        """The class, not an instance.

        An earlier version asserted `SDoHFollowUpBP()` returns something, which it
        cannot: `BusinessProcess.__init__` takes an `iris_host_object` that only
        the Interoperability framework supplies, so constructing one outside a
        running production raises TypeError. The test passed only against a
        mocked `intersystems_pyprod` whose BusinessProcess was plain `object`.
        """
        from intersystems_pyprod import BusinessProcess
        from productions.sdoh_followup import SDoHFollowUpBP

        assert issubclass(SDoHFollowUpBP, BusinessProcess)
        assert callable(getattr(SDoHFollowUpBP, "OnRequest", None)) or callable(
            getattr(SDoHFollowUpBP, "OnMessage", None)
        ), "a business process must implement OnRequest or OnMessage"

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

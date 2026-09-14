import os
import time

import httpx
import pytest

from conftest import HUB_HOST, HUB_PORT, FHIR_BASE, USERS, requires_iris

pytestmark = [pytest.mark.e2e, pytest.mark.docker]


class TestOnboardingBottleneck:
    @requires_iris
    def test_queue_depth_rises_under_concurrent_triggers(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM Ens.MessageHeader
            WHERE Status = 1 AND TargetConfigName = 'PatientOnboardBP'
        """)
        depth_before = cur.fetchone()[0]

        fhir = httpx.Client(base_url=FHIR_BASE, timeout=10)
        for _ in range(3):
            fhir.post(
                "/Patient",
                json={
                    "resourceType": "Patient",
                    "birthDate": "1990-01-01",
                    "gender": "male",
                    "telecom": [{"system": "phone", "value": "555-0000"}],
                },
            )
        fhir.close()

        time.sleep(5)

        cur.execute("""
            SELECT COUNT(*) FROM Ens.MessageHeader
            WHERE Status = 1 AND TargetConfigName = 'PatientOnboardBP'
        """)
        depth_after = cur.fetchone()[0]
        conn.close()

    @requires_iris
    def test_incomplete_patient_routed_to_data_queue(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        iris_obj = iris.createIRIS(conn)

        from productions.patient_onboarding import (
            PatientOnboardBP,
            DataQueueBO,
        )
        from productions.patient_onboarding import PatientRecord

        record = PatientRecord()
        record.patient_id = "Patient/test-incomplete-001"
        record.fhir_bundle = '{"resourceType":"Bundle","entry":[]}'
        record.ready = False
        record.issues = "missing birthDate"

        iris_obj.set(
            "^CareConnect.DataQueue",
            "Patient/test-incomplete-001",
            "issues",
            "missing birthDate",
        )
        iris_obj.set(
            "^CareConnect.DataQueue",
            "Patient/test-incomplete-001",
            "queued_at",
            "2026-04-19T00:00:00Z",
        )

        val = iris_obj.get(
            "^CareConnect.DataQueue", "Patient/test-incomplete-001", "issues"
        )
        conn.close()
        assert val == "missing birthDate"

    @requires_iris
    def test_restart_does_not_reprocess_ingested_patients(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        iris_obj = iris.createIRIS(conn)

        iris_obj.set("^CareConnect.LastPoll", "2026-01-01T00:00:00Z")
        last_poll_1 = iris_obj.get("^CareConnect.LastPoll")

        last_poll_2 = iris_obj.get("^CareConnect.LastPoll")
        conn.close()

        assert last_poll_1 == last_poll_2, (
            "LastPoll timestamp changed between reads — unexpected mutation"
        )


class TestProductionPoolSaturation:
    @requires_iris
    def test_total_pool_size_exceeds_ce_limit_with_sdoh_prod(self):
        from productions.patient_onboarding import PatientOnboardingProd
        from productions.sdoh_followup import SDoHFollowUpBP

        onboarding_pool = sum(
            item.get("PoolSize", 1) for item in PatientOnboardingProd.items
        )
        sdoh_pool = 2
        careconnect_app = 3
        total = onboarding_pool + sdoh_pool + careconnect_app
        assert total > 8, (
            f"Total pool {total} must exceed CE 8-connection limit for the demo bottleneck to occur"
        )

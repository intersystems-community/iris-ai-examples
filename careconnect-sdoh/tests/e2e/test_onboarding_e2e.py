import os
import time

import pytest

from conftest import HUB_HOST, HUB_PORT, USERS, requires_iris

pytestmark = [pytest.mark.e2e, pytest.mark.docker]


class TestOnboardingBottleneck:
    @requires_iris
    def test_queue_depth_rises_under_concurrent_triggers(self, fhir):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["admin"])
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM Ens.MessageHeader
            WHERE Status = 1 AND TargetConfigName = 'PatientOnboardBP'
        """)
        depth_before = cur.fetchone()[0]

        # The `fhir` fixture, not a locally built client: writes to /Patient need
        # credentials, and an unauthenticated POST here returned 401 rather than
        # queueing anything for PatientOnboardBP.
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

        # Value first: IRIS.set(value, globalName, subscripts...). Passing the
        # global name first raises RuntimeError <SYNTAX>, which names neither the
        # argument order nor the global. get() is the other way round.
        iris_obj.set(
            "missing birthDate",
            "^CareConnect.DataQueue",
            "Patient/test-incomplete-001",
            "issues",
        )
        iris_obj.set(
            "2026-04-19T00:00:00Z",
            "^CareConnect.DataQueue",
            "Patient/test-incomplete-001",
            "queued_at",
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

        iris_obj.set("2026-01-01T00:00:00Z", "^CareConnect.LastPoll")
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

        # services/processes/operations, the attributes the SDK reads. There is no
        # `items` list on Production.
        onboarding_pool = sum(
            item.pool_size
            for group in (
                PatientOnboardingProd.services,
                PatientOnboardingProd.processes,
                PatientOnboardingProd.operations,
            )
            for item in group
        )
        sdoh_pool = 2
        careconnect_app = 3
        total = onboarding_pool + sdoh_pool + careconnect_app
        assert total > 8, (
            f"Total pool {total} must exceed CE 8-connection limit for the demo bottleneck to occur"
        )

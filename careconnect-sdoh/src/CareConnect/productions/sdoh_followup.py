"""
CareConnect — SDoHFollowUpBP production (pyprod)

Programmatic IRIS Interoperability production for SDoH care coordination.
Loaded into iris-ai-hub container via pyprod on startup.

Triggered by:
  - CareConnect.Tools.SDoHToolSet.TriggerFollowUp() (ObjectScript)
  - objectscript-mcp trigger_workflow tool (MCP)
  - Direct pyprod call from Python

Three components:
  SDoHFollowUpBS  — Business Service: receives requests, validates, routes
  SDoHFollowUpBP  — Business Process: orchestrates consent → scheduling → FHIR
  SDoHFollowUpBO  — Business Operation: writes CarePlan back to FHIR repository
"""

import os
from intersystems_pyprod import (
    BusinessService,
    BusinessProcess,
    BusinessOperation,
    Status,
    ProductionMessage,
)

_FHIR_BASE = os.environ.get(
    "FHIR_BASE_URL", "http://iris-fhir:52773/csp/healthshare/demo/fhir/r4"
)


class FollowUpRequest(ProductionMessage):
    patient_id: str = ""
    priority: str = "routine"
    sdoh_flags: str = ""
    requested_by: str = ""
    job_id: str = ""


class FollowUpResponse(ProductionMessage):
    job_id: str = ""
    status: str = ""
    care_plan_id: str = ""
    error: str = ""


class SDoHFollowUpBS(BusinessService):
    """
    Entry point — receives FollowUpRequest, validates required fields,
    forwards to SDoHFollowUpBP.
    """

    def OnProcessInput(self, request: FollowUpRequest):
        if not request.patient_id:
            return Status.Error("patient_id is required"), None

        valid_priorities = {"routine", "urgent", "emergent"}
        if request.priority not in valid_priorities:
            request.priority = "routine"

        import uuid

        request.job_id = str(uuid.uuid4())[:8]

        response = FollowUpResponse()
        sc = yield self.SendRequestSync("SDoHFollowUpBP", request, response)
        return sc, response


class SDoHFollowUpBP(BusinessProcess):
    """
    Orchestrates three sequential steps:
      1. ConsentCheck  — verify patient consent for SDoH outreach
      2. CHWSchedule   — find available CHW and schedule contact
      3. FHIRCarePlan  — write CarePlan resource back to FHIR
    """

    def OnRequest(self, request: FollowUpRequest):
        consent = ConsentRequest()
        consent.patient_id = request.patient_id
        consent_resp = ConsentResponse()
        sc = yield self.SendRequestSync("SDoHConsentBO", consent, consent_resp)
        if Status.IsError(sc) or not consent_resp.approved:
            response = FollowUpResponse()
            response.job_id = request.job_id
            response.status = "blocked"
            response.error = "Consent not obtained or denied"
            return Status.OK(), response

        schedule = ScheduleRequest()
        schedule.patient_id = request.patient_id
        schedule.priority = request.priority
        schedule.sdoh_flags = request.sdoh_flags
        schedule_resp = ScheduleResponse()
        sc = yield self.SendRequestSync("SDoHSchedulerBO", schedule, schedule_resp)
        if Status.IsError(sc):
            response = FollowUpResponse()
            response.job_id = request.job_id
            response.status = "scheduling_failed"
            return sc, response

        fhir_req = FHIRCarePlanRequest()
        fhir_req.patient_id = request.patient_id
        fhir_req.chw_id = schedule_resp.chw_id
        fhir_req.sdoh_flags = request.sdoh_flags
        fhir_req.priority = request.priority
        fhir_req.requested_by = request.requested_by
        fhir_resp = FHIRCarePlanResponse()
        sc = yield self.SendRequestSync("SDoHFHIRCarePlanBO", fhir_req, fhir_resp)

        response = FollowUpResponse()
        response.job_id = request.job_id
        response.status = "completed" if not Status.IsError(sc) else "fhir_write_failed"
        response.care_plan_id = fhir_resp.care_plan_id
        return Status.OK(), response


class SDoHFHIRCarePlanBO(BusinessOperation):
    """
    Writes a FHIR CarePlan resource to iris-fhir.
    Uses standard FHIR REST API — no IRIS-specific dependencies.
    """

    def OnMessage(self, request: "FHIRCarePlanRequest"):
        import httpx
        import json
        from datetime import date

        care_plan = {
            "resourceType": "CarePlan",
            "status": "active",
            "intent": "plan",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "734163000",
                            "display": "Care plan",
                        }
                    ]
                }
            ],
            "subject": {"reference": f"Patient/{request.patient_id}"},
            "period": {"start": date.today().isoformat()},
            "author": {"display": request.requested_by or "CareConnect"},
            "note": [
                {
                    "text": f"SDoH follow-up care plan.\n"
                    f"CHW assigned: {request.chw_id}\n"
                    f"SDoH flags: {request.sdoh_flags}\n"
                    f"Priority: {request.priority}"
                }
            ],
        }

        resp = httpx.post(
            f"{_FHIR_BASE}/CarePlan",
            json=care_plan,
            headers={"Content-Type": "application/fhir+json"},
            timeout=10,
        )
        resp.raise_for_status()

        fhir_resp = FHIRCarePlanResponse()
        fhir_resp.care_plan_id = resp.json().get("id", "unknown")
        return Status.OK(), fhir_resp


class ConsentRequest(ProductionMessage):
    patient_id: str = ""


class ConsentResponse(ProductionMessage):
    approved: bool = True


class ScheduleRequest(ProductionMessage):
    patient_id: str = ""
    priority: str = "routine"
    sdoh_flags: str = ""


class ScheduleResponse(ProductionMessage):
    chw_id: str = ""


class FHIRCarePlanRequest(ProductionMessage):
    patient_id: str = ""
    chw_id: str = ""
    sdoh_flags: str = ""
    priority: str = "routine"
    requested_by: str = ""


class FHIRCarePlanResponse(ProductionMessage):
    care_plan_id: str = ""


def load_production(conn=None):
    """
    Load and start the SDoH follow-up production into iris-ai-hub.
    Called from the container init script.

    Usage:
        import iris
        conn = iris.connect('iris-ai-hub', 1973, 'USER', '_SYSTEM', 'SYS')
        from careconnect.productions.sdoh_followup import load_production
        load_production(conn)
    """
    import sys
    import subprocess

    components = [
        SDoHFollowUpBS,
        SDoHFollowUpBP,
        SDoHFHIRCarePlanBO,
    ]

    script_path = "/tmp/careconnect_sdoh_followup.py"
    module_path = __file__

    cmd = ["intersystems_pyprod", module_path]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error loading production: {result.stderr}")
        return False

    print("SDoH follow-up production loaded.")
    print(result.stdout)
    return True

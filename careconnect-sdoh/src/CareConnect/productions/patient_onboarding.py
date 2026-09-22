import os
import json
import time
from datetime import datetime, timedelta
from intersystems_pyprod import (
    BusinessService, BusinessProcess, BusinessOperation,
    Production, Status, ProductionMessage,
    ServiceItem, ProcessItem, OperationItem,
)

_FHIR_BASE  = os.environ.get("FHIR_BASE_URL", "http://iris-fhir:52773/csp/healthshare/demo/fhir/r4")
_POLL_SECS  = int(os.environ.get("FHIR_POLL_SECONDS", "30"))
_INGEST_POOL = int(os.environ.get("FHIR_INGEST_POOL", "3"))


class PatientPollRequest(ProductionMessage):
    since:      str = ""
    batch_size: int = 10

class PatientRecord(ProductionMessage):
    patient_id:  str = ""
    fhir_bundle: str = ""
    ready:       bool = False
    issues:      str = ""

class IngestResult(ProductionMessage):
    patient_id: str = ""
    kg_node_id: str = ""
    status:     str = ""
    error:      str = ""


class FHIRPollingBS(BusinessService):
    """
    Polls iris-fhir every FHIR_POLL_SECONDS for newly updated patients.
    Fires one PatientPollRequest per polling cycle.

    Uses ^CareConnect.LastPoll global to track the last run timestamp
    so restarts don't re-process the entire repository.

    Community Edition note: this service holds 1 connection slot.
    Combined with FHIRIngestBO (PoolSize=3) = 4 slots used.
    Leave headroom for careconnect app queries (2-3 slots).
    """

    def OnInit(self):
        return Status.OK()

    def OnProcessInput(self, message):
        iris_obj = self._get_iris()
        last_poll = iris_obj.get("^CareConnect.LastPoll") or ""
        if not last_poll:
            last_poll = (datetime.now() - timedelta(hours=24)).isoformat()[:19] + "Z"

        req = PatientPollRequest()
        req.since      = last_poll
        req.batch_size = 20

        sc, _ = yield self.SendRequestSync("PatientOnboardBP", req)

        iris_obj.set("^CareConnect.LastPoll", datetime.utcnow().isoformat()[:19] + "Z")
        return sc

    def _get_iris(self):
        import iris
        return iris.createIRIS(iris.connect(
            os.environ.get("IRIS_HUB_HOST","iris-ai-hub"),
            int(os.environ.get("IRIS_HUB_PORT","1973")),
            os.environ.get("IRIS_HUB_NAMESPACE","USER"),
            os.environ.get("IRIS_HUB_USERNAME","_SYSTEM"),
            os.environ.get("IRIS_HUB_PASSWORD","SYS"),
        ))


class PatientOnboardBP(BusinessProcess):
    """
    Orchestrates patient onboarding:
      1. Fetch new/updated patients from iris-fhir since last poll
      2. For each patient: fetch full record via $everything
      3. Run FHIR readiness check (5 deterministic checks)
      4. If ready  → route to FHIRIngestBO for KG embedding
         If not ready → route to DataQueueBO for remediation tracking

    This is the production that creates the interesting load pattern:
    under concurrent CHW sessions, FHIRIngestBO's HTTP adapter pool
    (PoolSize=3) saturates the Community Edition 8-connection limit.
    The backlog appears as queue depth on ^Ens.Queue["PatientOnboardBP"].
    """

    def OnRequest(self, request: PatientPollRequest):
        import httpx
        try:
            r = httpx.get(
                f"{_FHIR_BASE}/Patient",
                params={"_since": request.since, "_count": request.batch_size},
                timeout=10,
            )
            r.raise_for_status()
            bundle = r.json()
        except Exception as e:
            self.log_warning(f"FHIR poll failed: {e}")
            return Status.OK()

        entries = [e["resource"] for e in bundle.get("entry", [])]
        self.log_info(f"Polled {len(entries)} patients since {request.since}")

        for patient in entries:
            pid = patient.get("id", "")
            if not pid:
                continue

            try:
                everything = httpx.get(
                    f"{_FHIR_BASE}/Patient/{pid}/$everything",
                    params={"_count": 50},
                    timeout=10,
                )
                everything.raise_for_status()
                fhir_bundle = everything.text
            except Exception as e:
                self.log_warning(f"$everything failed for {pid}: {e}")
                fhir_bundle = json.dumps({"resourceType": "Bundle", "entry": [{"resource": patient}]})

            record = PatientRecord()
            record.patient_id  = pid
            record.fhir_bundle = fhir_bundle
            record.ready, record.issues = self._readiness_check(patient)

            if record.ready:
                yield self.SendRequestAsync("FHIRIngestBO", record)
            else:
                yield self.SendRequestAsync("DataQueueBO", record)

        return Status.OK()

    @staticmethod
    def _readiness_check(patient: dict) -> tuple[bool, str]:
        """Pure data rule — static so it can be tested without an IRIS host object.

        `BusinessProcess.__init__` requires an `iris_host_object`, which only the
        Interoperability framework can supply, so `PatientOnboardBP()` raises
        TypeError outside a running production. The readiness rule reads nothing
        off `self`, so there is no reason for a test of it to need a live host.
        """
        issues = []
        if not patient.get("birthDate"):
            issues.append("missing birthDate")
        if not patient.get("gender"):
            issues.append("missing gender")
        if not patient.get("telecom"):
            issues.append("no contact point")
        return (len(issues) == 0), ", ".join(issues)


class FHIRIngestBO(BusinessOperation):
    """
    Embeds a patient FHIR bundle into the IVG knowledge graph.

    PoolSize=3 — this is where the Community Edition bottleneck appears.
    Three concurrent workers × 1 HTTP connection each = 3 of 8 slots used.
    When SDoHFollowUpProd adds 2 more + careconnect app adds 2-3 more,
    the pool is exhausted and queue depth on PatientOnboardBP rises.

    The opsreview agent surfaces this as a HIGH severity bottleneck.
    """

    def OnMessage(self, request: PatientRecord):
        try:
            bundle = json.loads(request.fhir_bundle)
            summary = self._summarize_bundle(bundle)
            node_id = self._write_kg_node(request.patient_id, summary)

            result = IngestResult()
            result.patient_id = request.patient_id
            result.kg_node_id = node_id
            result.status     = "ingested"
            return Status.OK(), result
        except Exception as e:
            result = IngestResult()
            result.patient_id = request.patient_id
            result.status     = "error"
            result.error      = str(e)
            self.log_error(f"Ingest failed for {request.patient_id}: {e}")
            return Status.Error(str(e)), result

    def _summarize_bundle(self, bundle: dict) -> str:
        parts = []
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            rtype = r.get("resourceType", "")
            if rtype == "Condition":
                parts.append("Condition: " + r.get("code",{}).get("text",""))
            elif rtype == "Observation":
                parts.append("Obs: " + r.get("code",{}).get("text",""))
            elif rtype == "DocumentReference":
                parts.append("Note: " + r.get("description","")[:100])
        return "\n".join(parts[:20])

    def _write_kg_node(self, patient_id: str, summary: str) -> str:
        import iris
        iris_obj = iris.createIRIS(iris.connect(
            os.environ.get("IRIS_HUB_HOST","iris-ai-hub"),
            int(os.environ.get("IRIS_HUB_PORT","1973")),
            os.environ.get("IRIS_HUB_NAMESPACE","USER"),
            os.environ.get("IRIS_HUB_USERNAME","_SYSTEM"),
            os.environ.get("IRIS_HUB_PASSWORD","SYS"),
        ))
        node_id = f"patient-{patient_id}"
        iris_obj.set("^CareConnect.KG", node_id, "summary", summary)
        iris_obj.set("^CareConnect.KG", node_id, "ingested_at", datetime.utcnow().isoformat())
        return node_id


class DataQueueBO(BusinessOperation):
    """
    Tracks patients who failed the FHIR readiness check.
    Written to ^CareConnect.DataQueue global.
    Surfaced in opsreview as "data quality backlog" metric.
    """

    def OnMessage(self, request: PatientRecord):
        import iris
        iris_obj = iris.createIRIS(iris.connect(
            os.environ.get("IRIS_HUB_HOST","iris-ai-hub"),
            int(os.environ.get("IRIS_HUB_PORT","1973")),
            os.environ.get("IRIS_HUB_NAMESPACE","USER"),
            os.environ.get("IRIS_HUB_USERNAME","_SYSTEM"),
            os.environ.get("IRIS_HUB_PASSWORD","SYS"),
        ))
        ts = datetime.utcnow().isoformat()
        iris_obj.set("^CareConnect.DataQueue", request.patient_id, "issues",   request.issues)
        iris_obj.set("^CareConnect.DataQueue", request.patient_id, "queued_at", ts)
        self.log_info(f"Data queue: {request.patient_id} — {request.issues}")
        return Status.OK()


class PatientOnboardingProd(Production):
    """Hosts are declared per kind. There is no `items` list on Production.

    An earlier version set `items = [{"ClassName": ..., "PoolSize": ...}]`, which
    intersystems_pyprod ignores — it warns "There is no attribute named items for
    Production class" at import and then deploys a production with no hosts, so
    the intentional FHIRIngestBO bottleneck never materializes.
    """

    services = [
        ServiceItem(
            "FHIRPollingBS",
            "patient_onboarding.FHIRPollingBS",
            pool_size=1,
            host_settings={"CallInterval": str(_POLL_SECS)},
        ),
    ]

    processes = [
        ProcessItem("PatientOnboardBP", "patient_onboarding.PatientOnboardBP", pool_size=2),
    ]

    operations = [
        # PoolSize 3 is deliberate: it is the CE saturation bottleneck this
        # example exists to demonstrate (spec FR-003).
        OperationItem(
            "FHIRIngestBO", "patient_onboarding.FHIRIngestBO", pool_size=_INGEST_POOL
        ),
        OperationItem("DataQueueBO", "patient_onboarding.DataQueueBO", pool_size=1),
    ]


def load_production():
    import subprocess, sys
    result = subprocess.run(
        ["intersystems_pyprod", __file__],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        return False
    print(result.stdout)
    return True


if __name__ == "__main__":
    load_production()

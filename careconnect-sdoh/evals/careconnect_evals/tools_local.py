"""Offline, faithful Python port of CareConnect.Tools.SDoHToolSet.

CANONICAL SOURCE: ../../src/CareConnect/Tools/SDoHToolSet.cls (ObjectScript).
This module re-implements the same logic in pure Python so the eval harness can
run with zero infrastructure (no Docker, no IRIS, no API key).

It is a *faithful* port — including the tools' current quirks and bugs — because
an eval is only honest if it exercises the same behaviour the real system ships.
`tests/test_parity.py` (optional, requires a running IRIS) checks this port
against the live ObjectScript tools so the two cannot silently drift.

The same patient data lives in CareConnect.Setup.DemoData.cls.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field

from .liquid_decision import LiquidDecisionError, decide_with_d1

# --- Demo patients (mirror of CareConnect.Setup.DemoData.Load) ---------------

PATIENTS = {
    "maria-gonzalez-001": {
        "Name": "Maria Gonzalez",
        "Demographics": "42F",
        "Conditions": "Type 2 Diabetes Mellitus|Hypertension",
        "Observations": "HbA1c = 8.9|Blood Pressure = 148/92",
        "SDoHFlags": "food_insecurity|no_transport|unemployed",
        "Notes": (
            "Patient reports difficulty affording insulin. Lives alone, no "
            "transport. Recently lost job, relying on food bank. Primary "
            "language Spanish, limited English."
        ),
    },
    "james-okafor-002": {
        "Name": "James Okafor",
        "Demographics": "67M",
        "Conditions": "Congestive Heart Failure|Depression",
        "Observations": "BNP = 540|PHQ-9 = 14",
        "SDoHFlags": "social_isolation|housing_issues|medication_cost",
        "Notes": (
            "Socially isolated since wife passed. Lives in subsidized housing "
            "with mold issues. Skipping medications due to cost. No family nearby."
        ),
    },
    "sarah-kim-003": {
        "Name": "Sarah Kim",
        "Demographics": "29F",
        "Conditions": "Prenatal care 28wk|Iron deficiency anemia",
        "Observations": "Hemoglobin = 9.8",
        "SDoHFlags": "uninsured|food_insecurity|unstable_housing",
        "Notes": (
            "Uninsured, recently immigrated. Food insecure - skipping meals. "
            "No stable housing, staying with relatives. Transport barrier to clinic."
        ),
    },
}

# --- The SDoH rule (mirror of AssessSDoHRisk) --------------------------------
# One table rather than six inline conditionals, so `tests/test_parity_static.py`
# can compare it against the ObjectScript without a running IRIS. That test is
# the reason this is data: the live parity test skips whenever IRIS is absent,
# which is precisely when the mirror drifts.
#
# Keyword order matters only for the parity test; the rule is an OR.
DOMAIN_RULES = {
    "Economic Stability": {
        "keywords": ("unemploy", "job", "income", "afford"),
        "hit": "HIGH",
        "miss": "LOW",
    },
    "Education Access": {
        "keywords": ("english", "language", "literacy"),
        "hit": "HIGH",
        "miss": "LOW",
    },
    # The only domain that floors at MEDIUM: absence of evidence is not scored as
    # low risk for access to care.
    "Health Care Access": {
        "keywords": ("uninsur", "no doctor", "clinic"),
        "hit": "HIGH",
        "miss": "MEDIUM",
    },
    "Neighborhood/Built Env": {
        "keywords": ("housing", "mold", "unsafe", "food bank"),
        "hit": "HIGH",
        "miss": "LOW",
    },
    "Social Context": {
        "keywords": ("alone", "isolat", "no family", "no support"),
        "hit": "HIGH",
        "miss": "LOW",
    },
    "Transportation Access": {
        "keywords": (
            "no car",
            "no ride",
            "no bus",
            "transport",
            "transit",
            "missed appointment",
            "can't get to",
            "cannot get to",
        ),
        "hit": "HIGH",
        "miss": "LOW",
    },
}

DOMAIN_ORDER = list(DOMAIN_RULES)

# Evaluated in order; first threshold met wins. Six domains, so URGENT needs five.
PRIORITY_THRESHOLDS = (("URGENT", 5), ("HIGH", 3))

# The ObjectScript pads every label to the same column. One formula reproduces
# all six literals, and keeps doing so when a seventh domain arrives.
_LABEL_WIDTH = 25


def assessment_line(label: str, value: str) -> str:
    """One line of the printed assessment block, byte-identical to the
    ObjectScript's hand-written literal."""
    return f"  {label + ':':<{_LABEL_WIDTH}}{value}"


# --- Tool schemas (provider-neutral) -----------------------------------------
# Mirrors the <Tool> entries in SDoHToolSet.cls XData. Providers translate this
# neutral shape into Anthropic / OpenAI tool-definition formats.

TOOL_SCHEMAS = [
    {
        "name": "SearchPatients",
        "description": "List all demo patients or search by name, condition, or "
        "patient ID. Returns patientId values for use with FetchPatientSummary.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Optional search term"}},
        },
    },
    {
        "name": "FetchPatientSummary",
        "description": "Fetch clinical conditions, observations, and social "
        "context for a patient from the demo database.",
        "parameters": {
            "type": "object",
            "properties": {"patientId": {"type": "string"}},
            "required": ["patientId"],
        },
    },
    {
        "name": "SearchSDoHProtocols",
        "description": "Search the SDoH protocol knowledge base for screening "
        "guidelines that match the patient conditions.",
        "parameters": {
            "type": "object",
            "properties": {"conditions": {"type": "string"}},
            "required": ["conditions"],
        },
    },
    {
        "name": "AssessSDoHRisk",
        "description": "Score a patient on six SDoH domains (five USDHHS plus "
        "transportation access) using clinical summary and matched protocols.",
        "parameters": {
            "type": "object",
            "properties": {
                "patientId": {"type": "string"},
                "clinicalSummary": {"type": "string"},
                "protocolMatches": {"type": "string"},
            },
            "required": ["patientId", "clinicalSummary"],
        },
    },
    {
        "name": "DraftCarePlan",
        "description": "Draft an actionable care plan with prioritized steps for "
        "the community health worker based on SDoH risk scores.",
        "parameters": {
            "type": "object",
            "properties": {
                "patientId": {"type": "string"},
                "sdohScores": {"type": "string"},
            },
            "required": ["patientId", "sdohScores"],
        },
    },
    {
        "name": "DecideCareAction",
        "description": "Choose EXECUTE, SIMULATE, ASK_HUMAN, or REJECT for a proposed "
        "follow-up using bounded confidence, consent, and policy.",
        "parameters": {
            "type": "object",
            "properties": {
                "patientId": {"type": "string"},
                "riskAssessment": {"type": "string"},
                "proposedAction": {"type": "string"},
                "confidence": {"type": "string"},
                "consent": {"type": "string"},
            },
            "required": ["patientId", "riskAssessment"],
        },
    },
    {
        "name": "StartProduction",
        "description": "Start the CareConnect IRIS Interoperability production. "
        "Safe to call if already running.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "GetProductionStatus",
        "description": "Get the current status of the CareConnect production.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "TriggerFollowUp",
        "description": "Trigger an SDoH follow-up workflow via the IRIS "
        "Interoperability production.",
        "parameters": {
            "type": "object",
            "properties": {
                "patientId": {"type": "string"},
                "priority": {"type": "string"},
                "sdohFlags": {"type": "string"},
            },
            "required": ["patientId"],
        },
    },
    {
        "name": "GetInteropTraces",
        "description": "Show recent IRIS Interoperability message traces.",
        "parameters": {
            "type": "object",
            "properties": {"maxRows": {"type": "string"}},
        },
    },
    {
        "name": "SearchClinicalNotes",
        "description": "Search FHIR DocumentReference clinical notes for a "
        "patient. Returns matching note summaries. Requires the FHIR server to "
        "be running.",
        "parameters": {
            "type": "object",
            "properties": {
                "patientId": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["patientId"],
        },
    },
]

# One DocumentReference per demo patient, standing in for what the FHIR server
# holds. Fixed dates, because an eval that moves with the calendar is not a
# regression test.
CLINICAL_NOTE_DATES = {
    "maria-gonzalez-001": "2026-02-14",
    "james-okafor-002": "2026-01-30",
    "sarah-kim-003": "2026-03-02",
}


# --- Tool client (faithful port + offline interop simulator) -----------------


@dataclass
class LocalToolClient:
    """Executes the ported tools in-process. Holds its own interop state so each
    eval run starts from a clean production (matching a fresh container)."""

    production_running: bool = False
    messages: list = field(default_factory=list)  # simulated Ens.MessageHeader rows
    liquid_mode: str = "mock"  # mock keeps the offline suite keyless; liquid calls d1

    # -- deterministic data tools --

    def SearchPatients(self, query: str = "") -> str:
        q = query.lower()
        if q == "":
            out = "Available patients (use patientId with FetchPatientSummary):\n"
            for pid, p in sorted(PATIENTS.items(), key=lambda kv: kv[1]["Name"]):
                out += f"  {pid} | {p['Name']} | {p['Demographics']} | {p['Conditions']}\n"
            return out
        out = ""
        for pid, p in PATIENTS.items():
            if q in p["Name"].lower() or q in p["Conditions"].lower() or query == pid:
                out += f"patientId: {pid}\n"
                out += f"  Name: {p['Name']}\n"
                out += f"  Demographics: {p['Demographics']}\n"
                out += f"  Conditions: {p['Conditions']}\n"
                out += f"  SDoH flags: {p['SDoHFlags']}\n\n"
        if out == "":
            return (
                f"No patients found matching '{query}'. Call SearchPatients with "
                "no arguments to list all."
            )
        return out

    def FetchPatientSummary(self, patientId: str, daysBack: str = "90") -> str:
        if not patientId:
            return "ERROR: patientId is required"
        p = PATIENTS.get(patientId)
        if not p:
            return f"Patient not found: {patientId}. Call SearchPatients to list available patients."
        out = f"Patient: {p['Name']}, {p['Demographics']}\n"
        for c in [x for x in p["Conditions"].split("|") if x]:
            out += f"Condition: {c}\n"
        for o in [x for x in p["Observations"].split("|") if x]:
            out += f"Observation: {o}\n"
        out += f"Note: {p['Notes']}"
        return out

    def SearchSDoHProtocols(self, conditions: str) -> str:
        if not conditions:
            return "ERROR: conditions is required"
        c = conditions.lower()
        out = ""
        if "diabetes" in c or "hba1c" in c or "glucose" in c:
            out += "Protocol: ADA Diabetes Distress Screening (Problem Areas in Diabetes scale)\n"
            out += "Protocol: Food Insecurity Screening - Hunger Vital Sign 2-item tool\n"
            out += "Protocol: AADE7 Self-Care Behaviors assessment for diabetes management barriers\n"
        if "hypertension" in c or "blood pressure" in c:
            out += "Protocol: AHA Hypertension Social Needs Screening Tool\n"
            out += "Protocol: Housing Instability Screening - iHELP instrument\n"
        if "heart" in c or "chf" in c or "bnp" in c:
            out += "Protocol: ACC/AHA Social Determinants of Cardiovascular Risk Protocol\n"
            out += "Protocol: Social Isolation and Loneliness Screening - UCLA Loneliness Scale (3-item)\n"
        if "depress" in c or "phq" in c or "mental" in c:
            out += "Protocol: PHQ-9 Depression Screening with SDoH integration workflow\n"
            out += "Protocol: Social Connection and Support Network Assessment\n"
        if "food" in c or "nutrition" in c or "anemia" in c:
            out += "Protocol: USDA Household Food Security Survey Module (2-item screen)\n"
            out += "Protocol: WIC Referral and Community Food Resource Navigation Protocol\n"
        if "housing" in c or "transport" in c or "financial" in c or "uninsured" in c:
            out += "Protocol: PRAPARE SDoH Screening Tool\n"
            out += "Protocol: Community Health Worker Navigation Referral Protocol\n"
        if out == "":
            out = "Protocol: PRAPARE Universal SDoH Screening Tool\n"
            out += "Protocol: NACHC Social Needs Screening and Referral Workflow\n"
        return out

    def AssessSDoHRisk(self, patientId: str, clinicalSummary: str, protocolMatches: str = "") -> str:
        if not patientId:
            return "ERROR: patientId is required"
        s = clinicalSummary.lower()
        scores = {
            label: rule["hit"] if any(k in s for k in rule["keywords"]) else rule["miss"]
            for label, rule in DOMAIN_RULES.items()
        }
        out = f"SDoH Risk Assessment for {patientId}:\n"
        for label in DOMAIN_ORDER:
            out += assessment_line(label, scores[label]) + "\n"
        high = sum(1 for v in scores.values() if v == "HIGH")
        priority = next((name for name, floor in PRIORITY_THRESHOLDS if high >= floor), "ROUTINE")
        out += f"Overall Priority: {priority} ({high}/{len(DOMAIN_RULES)} domains elevated)"
        return out

    def DraftCarePlan(self, patientId: str, sdohScores: str) -> str:
        if not patientId:
            return "ERROR: patientId is required"
        s = sdohScores.lower()
        out = f"Care Plan for {patientId}:\n\n"
        step = 1
        if "economic" in s:
            out += f"{step}. Connect with financial assistance programs - SNAP, Medicaid, emergency rental assistance\n"
            step += 1
        if "health care" in s or "transport" in s:
            out += f"{step}. Schedule CHW home visit within 5 days - assess transportation barriers\n"
            step += 1
            out += f"{step}. Enroll in patient transport program or telehealth if available\n"
            step += 1
        if "neighborhood" in s:
            out += f"{step}. Report housing issues to housing authority - document mold/safety concerns\n"
            step += 1
        if "social" in s or "isolat" in s:
            out += f"{step}. Refer to community social connection program - senior center, peer support group\n"
            step += 1
        out += f"{step}. Schedule 30-day follow-up call to assess progress on care plan goals\n"
        out += "\nPriority: Urgent if 5+ domains HIGH - escalate to supervising CHW"
        return out

    def DecideCareAction(
        self,
        patientId: str,
        riskAssessment: str,
        proposedAction: str = "trigger_follow_up",
        confidence: str = "0.90",
        consent: str = "no",
    ) -> str:
        """Use Liquid d1 when configured, with a deterministic offline fallback.

        This is intentionally separate from TriggerFollowUp: d1 decides what
        should happen, while the service's write policy decides who may make the
        actual change. The ObjectScript ToolSet exposes the same contract.
        """
        if not patientId:
            return "ERROR: patientId is required"
        if self.liquid_mode.lower() == "liquid":
            try:
                return decide_with_d1(
                    patientId,
                    riskAssessment,
                    proposedAction,
                    consent,
                    api_key=os.getenv("LIQUID_API_KEY", ""),
                    base_url=os.getenv("LIQUID_BASE_URL", "https://api.liquid.ai"),
                    model=os.getenv("LIQUID_DECISION_MODEL", "d1:free"),
                )
            except LiquidDecisionError as exc:
                return f"ERROR: Liquid d1 decision failed: {exc}"
        action = proposedAction.lower()
        if action != "trigger_follow_up":
            return f"Decision: REJECT\nReason: unsupported action '{proposedAction}'"
        risk = riskAssessment.lower()
        priority = "ROUTINE"
        if "overall priority: urgent" in risk:
            priority = "URGENT"
        elif "overall priority: high" in risk:
            priority = "HIGH"
        try:
            score = float(confidence)
        except (TypeError, ValueError):
            score = 0.0
        out = (
            f"Action Gate for {patientId} (offline mock)\n"
            f"Action: {action}\n"
            f"Priority: {priority}\n"
            f"Confidence: {confidence}\n"
        )
        if consent.lower() != "yes":
            return out + "Decision: ASK_HUMAN\nReason: patient consent is not confirmed"
        if score < 0.75:
            return out + "Decision: ASK_HUMAN\nReason: confidence is below the 0.75 decision threshold"
        if priority == "URGENT" and score >= 0.85:
            return out + "Decision: EXECUTE\nReason: urgent follow-up meets consent and confidence policy"
        if priority == "HIGH" and score >= 0.90:
            return out + "Decision: SIMULATE\nReason: high-priority action is eligible for simulation before a write"
        return out + "Decision: REJECT\nReason: no policy permits an automatic follow-up for this risk level"

    # -- FHIR tool (offline simulator of a DocumentReference search) --

    def SearchClinicalNotes(self, patientId: str, query: str = "") -> str:
        """Offline stand-in for the ObjectScript tool's FHIR round trip.

        The shipped tool GETs `DocumentReference?patient=<id>` off the demo FHIR
        server and prints `[status] date - description` per entry. There is no
        FHIR server here, so the demo patient's note is served as the single
        DocumentReference the server would return. Output shape matches the
        ObjectScript byte for byte; the transport does not, which is why
        `tests/test_parity.py` does not compare this one against a live IRIS —
        `tests/test_harness.py` pins it to a golden string instead.
        """
        if not patientId:
            return "ERROR: patientId is required"
        patient = PATIENTS.get(patientId)
        if patient is None:
            return f"No clinical notes found for patient {patientId}"
        note = patient["Notes"]
        if query and query.lower() not in note.lower():
            return f"No clinical notes found for patient {patientId}"
        date = CLINICAL_NOTE_DATES.get(patientId, "")
        return f"Clinical notes for {patientId}:\n  [current] {date} - {note}\n"

    # -- interop tools (offline simulator of Ens.Director + MessageHeader) --

    def StartProduction(self) -> str:
        if self.production_running:
            return "Production already running: CareConnect.Production"
        self.production_running = True
        return "Production started: CareConnect.Production (Running)"

    def GetProductionStatus(self) -> str:
        state = "Running" if self.production_running else "Stopped"
        return f"Production: CareConnect.Production\nStatus: {state}\n"

    def TriggerFollowUp(self, patientId: str, priority: str = "routine", sdohFlags: str = "") -> str:
        if not patientId:
            return "ERROR: patientId is required"
        if not self.production_running:
            return "Production is not running. Call StartProduction first, then retry."
        job_id = str(uuid.uuid4()).upper()
        # Simulate the BS -> BP -> BO -> BP -> BS message flow (4 headers).
        flow = [
            ("SDoHFollowUpBS", "SDoHFollowUpBP", "FollowUpRequest"),
            ("SDoHFollowUpBP", "SDoHFollowUpBO", "FollowUpRequest"),
            ("SDoHFollowUpBO", "SDoHFollowUpBP", "FollowUpResponse"),
            ("SDoHFollowUpBP", "SDoHFollowUpBS", "FollowUpResponse"),
        ]
        for src, tgt, cls in flow:
            self.messages.append(
                {"src": src, "tgt": tgt, "cls": cls, "status": "Completed", "patientId": patientId}
            )
        return f"Follow-up triggered for {patientId} (priority={priority}) jobId={job_id}"

    def GetInteropTraces(self, maxRows: str = "20", **_) -> str:
        if not self.messages:
            return "No messages found. Start the production with StartProduction, then call TriggerFollowUp."
        rows = self.messages[-int(maxRows or 20):]
        out = f"Interoperability Traces ({len(rows)}):\n"
        for i, m in enumerate(rows, 1):
            out += f"[{i}] {m['src']} -> {m['tgt']} | {m['cls']} | {m['status']}\n"
        return out

    # -- dispatcher used by the agent loop --

    def execute(self, name: str, args: dict) -> str:
        method = getattr(self, name, None)
        if method is None:
            return f"ERROR: unknown tool {name}"
        try:
            return method(**args)
        except TypeError as exc:
            return f"ERROR: bad arguments for {name}: {exc}"


def follow_up_fired(client: LocalToolClient, patientId: str) -> bool:
    """Layer-3 ground truth: did a follow-up workflow actually run for this
    patient? In a live system this reads Ens.MessageHeader."""
    return any(m["patientId"] == patientId for m in client.messages)


if __name__ == "__main__":  # quick smoke test
    c = LocalToolClient()
    print(c.SearchPatients())
    print(json.dumps([t["name"] for t in TOOL_SCHEMAS]))

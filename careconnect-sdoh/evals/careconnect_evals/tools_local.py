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
import uuid
from dataclasses import dataclass, field

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

DOMAIN_ORDER = [
    "Economic Stability",
    "Education Access",
    "Health Care Access",
    "Neighborhood/Built Env",
    "Social Context",
]


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
        "description": "Score a patient on all five USDHHS SDoH domains using "
        "clinical summary and matched protocols.",
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
]


# --- Tool client (faithful port + offline interop simulator) -----------------


@dataclass
class LocalToolClient:
    """Executes the 9 tools in-process. Holds its own interop state so each
    eval run starts from a clean production (matching a fresh container)."""

    production_running: bool = False
    messages: list = field(default_factory=list)  # simulated Ens.MessageHeader rows

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
        econ = "HIGH" if any(k in s for k in ("unemploy", "job", "income", "afford")) else "LOW"
        edu = "HIGH" if any(k in s for k in ("english", "language", "literacy")) else "LOW"
        health = "HIGH" if any(k in s for k in ("uninsur", "transport", "no doctor", "clinic")) else "MEDIUM"
        nbhd = "HIGH" if any(k in s for k in ("housing", "mold", "unsafe", "food bank")) else "LOW"
        social = "HIGH" if any(k in s for k in ("alone", "isolat", "no family", "no support")) else "LOW"
        out = f"SDoH Risk Assessment for {patientId}:\n"
        out += f"  Economic Stability:      {econ}\n"
        out += f"  Education Access:        {edu}\n"
        out += f"  Health Care Access:      {health}\n"
        out += f"  Neighborhood/Built Env:  {nbhd}\n"
        out += f"  Social Context:          {social}\n"
        high = sum(1 for d in (econ, edu, health, nbhd, social) if d == "HIGH")
        priority = "URGENT" if high >= 4 else "HIGH" if high >= 2 else "ROUTINE"
        out += f"Overall Priority: {priority} ({high}/5 domains elevated)"
        return out

    def DraftCarePlan(self, patientId: str, sdohScores: str) -> str:
        if not patientId:
            return "ERROR: patientId is required"
        s = sdohScores.lower()
        out = f"Care Plan for {patientId}:\n\n"
        step = 1
        if "economic" in s:
            out += f"{step}. Connect with financial assistance programs — SNAP, Medicaid, emergency rental assistance\n"
            step += 1
        if "health care" in s or "transport" in s:
            out += f"{step}. Schedule CHW home visit within 5 days — assess transportation barriers\n"
            step += 1
            out += f"{step}. Enroll in patient transport program or telehealth if available\n"
            step += 1
        if "neighborhood" in s:
            out += f"{step}. Report housing issues to housing authority — document mold/safety concerns\n"
            step += 1
        if "social" in s or "isolat" in s:
            out += f"{step}. Refer to community social connection program — senior center, peer support group\n"
            step += 1
        out += f"{step}. Schedule 30-day follow-up call to assess progress on care plan goals\n"
        out += "\nPriority: Urgent if 4+ domains HIGH — escalate to supervising CHW"
        return out

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

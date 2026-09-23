"""Formatters for CareConnect's legacy-bound tools in sidecar mode.

In sidecar mode the patient and interop tools answer from the legacy IRIS over
SQL and the Native API instead of from SDoHToolSet. These functions render
those results in exactly the text the ObjectScript tools print, so

* AssessSDoHRisk, a keyword scorer, sees the same summary text either way;
* the model sees the same tool output whichever topology answered;
* an eval written against one mode holds against the other.

tests/test_careconnect_modes.py pins each one against the offline mirror,
which the eval suite in turn pins against the ObjectScript.

Each SQL formatter takes ``(rows, args)``; each classmethod formatter takes
``(text, args)``.
"""

from __future__ import annotations

import json

# Ens.MessageHeader.Status, as SDoHToolSet.GetInteropTraces spells it.
_STATUS = {
    1: "Queued",
    2: "Delivered",
    3: "Acknowledged",
    4: "Error",
    5: "Discarded",
    6: "Aborted",
    7: "Suspended",
    8: "Cancelled",
    9: "Completed",
}


def _pieces(value) -> list[str]:
    """``$Piece`` iteration as the ObjectScript does it: stop at the first empty piece."""
    out = []
    for part in ("" if value is None else str(value)).split("|"):
        if part == "":
            break
        out.append(part)
    return out


def search_patients_all(rows: list[dict], args: dict) -> str:
    out = "Available patients (use patientId with FetchPatientSummary):\n"
    for r in rows:
        out += f"  {r['PatientId']} | {r['Name']} | {r['Demographics']} | {r['Conditions']}\n"
    return out


def search_patients_matches(rows: list[dict], args: dict) -> str:
    out = ""
    for r in rows:
        out += f"patientId: {r['PatientId']}\n"
        out += f"  Name: {r['Name']}\n"
        out += f"  Demographics: {r['Demographics']}\n"
        out += f"  Conditions: {r['Conditions']}\n"
        out += f"  SDoH flags: {r['SDoHFlags']}\n\n"
    return out


def patient_summary(rows: list[dict], args: dict) -> str:
    r = rows[0]
    out = f"Patient: {r['Name']}, {r['Demographics']}\n"
    for c in _pieces(r.get("Conditions")):
        out += f"Condition: {c}\n"
    for o in _pieces(r.get("Observations")):
        out += f"Observation: {o}\n"
    return out + f"Note: {r['Notes']}"


def interop_traces(rows: list[dict], args: dict) -> str:
    out = ""
    for r in rows:
        status = _STATUS.get(_int(r.get("Status")), f"Status:{r.get('Status')}")
        src = str(r.get("SourceConfigName") or "").split(".")[-1]
        tgt = str(r.get("TargetConfigName") or "").split(".")[-1]
        cls = str(r.get("MessageBodyClassName") or "").split(".")[-1]
        out += f"[{r['ID']}] {r['TimeCreated']} | {src} -> {tgt} | {cls} | {status}\n"
    return f"Interoperability Traces ({len(rows)}):\n" + out


def follow_up(text: str, args: dict) -> str:
    """AIHub.Legacy.Interop.Dispatch returns JSON; say what TriggerFollowUp says."""
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return f"ERROR processing: {text}"
    if result.get("status") == "not_running":
        return "Production is not running. Call StartProduction first, then retry."
    if result.get("status") != "ok":
        return f"ERROR processing: {result.get('error', text)}"
    job_id = (result.get("response") or {}).get("JobId", "")
    priority = args.get("priority") or "routine"
    return f"Follow-up triggered for {args['patientId']} (priority={priority}) jobId={job_id}"


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value

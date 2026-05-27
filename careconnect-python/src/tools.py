import os
from typing import Optional

import iris as iris_native
from iris_llm import ToolSet, tool


def _get_iris_connection():
    return iris_native.connect(
        hostname=os.environ.get("IRIS_HOST", "iris"),
        port=int(os.environ.get("IRIS_PORT", "1972")),
        namespace=os.environ.get("IRIS_NAMESPACE", "USER"),
        username=os.environ.get("IRIS_USERNAME", "_SYSTEM"),
        password=os.environ.get("IRIS_PASSWORD", "SYS"),
    )


DOMAIN_KEYWORDS = {
    "economic_stability": [
        "unemploy", "job loss", "income", "afford", "food stamp",
        "snap", "financial", "poverty", "evict", "debt",
    ],
    "education_access": [
        "english", "language barrier", "literacy", "ged", "dropout",
        "school", "education", "english as second", "esl",
    ],
    "healthcare_access": [
        "uninsur", "no insurance", "transport", "no doctor", "clinic",
        "copay", "deductible", "appointment", "wait list", "telehealth",
    ],
    "neighborhood_environment": [
        "housing", "mold", "unsafe", "food bank", "food desert",
        "crime", "homeless", "shelter", "roach", "lead", "evict",
    ],
    "social_context": [
        "alone", "isolat", "no family", "no support", "lonely",
        "widowed", "caregiver", "domestic", "violence", "abuse",
    ],
}

RISK_LEVELS = {0: "LOW", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "HIGH", 5: "HIGH"}


def _score_domain(text_lower: str, keywords: list[str]) -> tuple[str, list[str]]:
    matched = [kw for kw in keywords if kw in text_lower]
    level = "HIGH" if len(matched) >= 2 else "MEDIUM" if matched else "LOW"
    return level, matched


class SDoHPythonTools(ToolSet):

    @tool
    def list_patients(self, search: str = "") -> str:
        """
        List demo patients or search by name, condition, or patient ID.
        Returns patient IDs and demographics for use with assess_sdoh_risk.

        Args:
            search: Optional search term (name, condition, or patient ID).
                    Leave empty to list all patients.
        """
        conn = _get_iris_connection()
        cur = conn.cursor()
        if not search:
            cur.execute(
                "SELECT PatientId, Name, Demographics, Conditions "
                "FROM CareConnect.Patient ORDER BY Name"
            )
        else:
            term = f"%{search.lower()}%"
            cur.execute(
                "SELECT PatientId, Name, Demographics, Conditions "
                "FROM CareConnect.Patient "
                "WHERE LOWER(Name) LIKE ? OR LOWER(Conditions) LIKE ? OR PatientId = ?",
                [term, term, search],
            )
        rows = cur.fetchall()
        if not rows:
            return "No patients found. The demo data may not be loaded yet."
        lines = ["Available patients:"]
        for patient_id, name, demographics, conditions in rows:
            lines.append(f"  {patient_id} | {name} | {demographics}")
            lines.append(f"    Conditions: {conditions}")
        return "\n".join(lines)

    @tool
    def assess_sdoh_risk(self, patient_id: str) -> str:
        """
        Score a patient on all five USDHHS SDoH domains using Python-based
        keyword analysis over their clinical summary. Returns domain scores,
        overall priority (ROUTINE / HIGH / URGENT), and the evidence keywords
        that drove each score.

        Args:
            patient_id: The patient ID to assess (e.g. P001).
        """
        if not patient_id:
            return "ERROR: patient_id is required"

        conn = _get_iris_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT Name, Conditions, Observations, Notes "
            "FROM CareConnect.Patient WHERE PatientId = ?",
            [patient_id],
        )
        row = cur.fetchone()
        if not row:
            return f"Patient not found: {patient_id}. Call SearchPatients to list available patients."

        name, conditions, observations, notes = row
        full_text = " ".join(
            filter(None, [conditions, observations, notes])
        ).lower()

        results = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            level, evidence = _score_domain(full_text, keywords)
            results[domain] = {"level": level, "evidence": evidence}

        high_count = sum(1 for d in results.values() if d["level"] == "HIGH")
        priority = "URGENT" if high_count >= 4 else "HIGH" if high_count >= 2 else "ROUTINE"

        lines = [f"SDoH Risk Assessment for {name} ({patient_id}) — Python scoring:"]
        domain_labels = {
            "economic_stability": "Economic Stability    ",
            "education_access": "Education Access      ",
            "healthcare_access": "Health Care Access    ",
            "neighborhood_environment": "Neighborhood/Built Env",
            "social_context": "Social Context        ",
        }
        for domain, data in results.items():
            evidence_str = (
                f"  [{', '.join(data['evidence'][:3])}]" if data["evidence"] else ""
            )
            lines.append(
                f"  {domain_labels[domain]}: {data['level']}{evidence_str}"
            )
        lines.append(f"\nOverall Priority: {priority} ({high_count}/5 domains elevated)")
        lines.append(
            "\nNote: This Python tool uses keyword scoring. "
            "For production use, integrate structured SDoH questionnaire data."
        )
        return "\n".join(lines)

    @tool
    def fetch_community_resources(
        self,
        zip_code: str,
        need_category: Optional[str] = None,
    ) -> str:
        """
        Look up community resources available in a zip code for a given SDoH
        need category. Returns organization names, addresses, phone numbers,
        and services offered.

        Args:
            zip_code: 5-digit US zip code (e.g. "02115").
            need_category: Optional filter — one of: food, housing, transportation,
                           healthcare, mental_health, financial. If omitted, returns
                           resources across all categories.
        """
        prefix = zip_code[:3] if len(zip_code) >= 3 else "000"

        resource_db = {
            "021": [
                {"name": "Greater Boston Food Bank", "category": "food", "phone": "617-427-5200", "services": "Emergency food pantry, SNAP enrollment assistance"},
                {"name": "Heading Home", "category": "housing", "phone": "617-864-8140", "services": "Emergency shelter, rapid rehousing, eviction prevention"},
                {"name": "MBTA Ride Program", "category": "transportation", "phone": "617-222-5123", "services": "Paratransit for medical appointments"},
                {"name": "Boston Medical Center HealthNet", "category": "healthcare", "phone": "617-414-5110", "services": "Sliding-scale primary care, telehealth, care navigation"},
                {"name": "NAMI Massachusetts", "category": "mental_health", "phone": "617-580-7755", "services": "Peer support, crisis helpline, mental health navigation"},
            ],
            "100": [
                {"name": "City Harvest", "category": "food", "phone": "646-412-0600", "services": "Mobile food pantry, community fridge network"},
                {"name": "Coalition for the Homeless", "category": "housing", "phone": "212-776-2000", "services": "Drop-in center, street outreach, transitional housing"},
                {"name": "NYC Health + Hospitals", "category": "healthcare", "phone": "844-692-4692", "services": "Sliding-scale care, financial counseling, community health workers"},
            ],
        }

        fallback = [
            {"name": "Local 211 Helpline", "category": "all", "phone": "211", "services": "Call 211 for local resources — food, housing, health, crisis services"},
            {"name": "Community Health Center", "category": "healthcare", "phone": "Call 211", "services": "Federally Qualified Health Center — sliding-scale care"},
            {"name": "Area Agency on Aging", "category": "all", "phone": "eldercare.acl.gov", "services": "Services for adults 60+ — meals, transportation, caregiver support"},
        ]

        resources = resource_db.get(prefix, fallback)

        if need_category:
            resources = [r for r in resources if r["category"] in (need_category, "all")]
            if not resources:
                resources = fallback

        lines = [f"Community resources near {zip_code}"]
        if need_category:
            lines[0] += f" for {need_category.replace('_', ' ')}"
        lines.append("")
        for r in resources:
            lines.append(f"  {r['name']} ({r['category']})")
            lines.append(f"    Phone: {r['phone']}")
            lines.append(f"    Services: {r['services']}")
            lines.append("")
        lines.append("Source: Community resource database (demo data). Production use: 211.org API.")
        return "\n".join(lines)

    @tool
    def summarize_sdoh_findings(
        self,
        patient_id: str,
        risk_assessment: str,
        community_resources: Optional[str] = None,
    ) -> str:
        """
        Produce a structured, plain-language SDoH summary for a community health
        worker. Synthesizes the risk assessment and available resources into a
        prioritized action brief with specific next steps.

        Args:
            patient_id: Patient ID.
            risk_assessment: Output from assess_sdoh_risk.
            community_resources: Optional output from fetch_community_resources.
        """
        if not patient_id or not risk_assessment:
            return "ERROR: patient_id and risk_assessment are required"

        lines_in = risk_assessment.lower()
        urgent = "urgent" in lines_in
        high = "high" in lines_in and not urgent

        conn = _get_iris_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT Name, Demographics FROM CareConnect.Patient WHERE PatientId = ?",
            [patient_id],
        )
        row = cur.fetchone()
        name = row[0] if row else patient_id
        demographics = row[1] if row else ""

        priority_label = "URGENT — same-day outreach required" if urgent else \
                         "HIGH — outreach within 48 hours" if high else \
                         "ROUTINE — schedule standard follow-up"

        lines = [
            f"CHW Action Brief: {name} ({patient_id})",
            f"Demographics: {demographics}",
            f"Priority: {priority_label}",
            "",
            "--- Risk Summary ---",
        ]

        for line in risk_assessment.split("\n"):
            if any(d in line for d in ["Economic", "Education", "Health Care", "Neighborhood", "Social"]):
                lines.append(line)

        lines += ["", "--- Recommended Actions ---"]

        if urgent:
            lines.append("1. IMMEDIATE: Warm transfer to supervising CHW or social worker")
            lines.append("2. Document all HIGH-risk domains in care management system")

        action_num = 3 if urgent else 1
        if "economic" in lines_in and "high" in lines_in:
            lines.append(f"{action_num}. Connect with financial assistance navigator (SNAP, Medicaid, emergency rental)")
            action_num += 1
        if "health care" in lines_in and "high" in lines_in:
            lines.append(f"{action_num}. Schedule CHW home visit — assess transportation and insurance barriers")
            action_num += 1
        if "neighborhood" in lines_in and "high" in lines_in:
            lines.append(f"{action_num}. Report housing concerns — document and refer to housing authority")
            action_num += 1
        if "social" in lines_in and "high" in lines_in:
            lines.append(f"{action_num}. Refer to social connection program — peer support or senior center")
            action_num += 1

        lines.append(f"{action_num}. Schedule 30-day follow-up call to assess progress")

        if community_resources:
            lines += ["", "--- Local Resources ---"]
            for rline in community_resources.split("\n")[1:6]:
                if rline.strip():
                    lines.append(f"  {rline.strip()}")

        lines += [
            "",
            "--- Documentation ---",
            "Record this assessment in the care management platform.",
            "Flag for care team review if priority is URGENT or HIGH.",
        ]

        return "\n".join(lines)

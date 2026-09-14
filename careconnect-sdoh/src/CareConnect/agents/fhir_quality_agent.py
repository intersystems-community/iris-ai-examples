import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx
import iris
from langchain_intersystems.chat_models import init_chat_model

_FHIR_BASE  = os.environ.get("FHIR_BASE_URL", "http://iris-fhir:52773/csp/healthshare/demo/fhir/r4")
_IRIS_HOST  = os.environ.get("IRIS_HUB_HOST",      "iris-ai-hub")
_IRIS_PORT  = int(os.environ.get("IRIS_HUB_PORT",  "1973"))
_IRIS_NS    = os.environ.get("IRIS_HUB_NAMESPACE", "USER")
_IRIS_USER  = os.environ.get("IRIS_HUB_USERNAME",  "_SYSTEM")
_IRIS_PASS  = os.environ.get("IRIS_HUB_PASSWORD",  "SYS")
_LLM_CONFIG = os.environ.get("LLM_CONFIG_NAME",    "openai")
_SAMPLE     = 20


@dataclass
class Check:
    name:    str
    passed:  bool
    pct:     float
    detail:  str
    fix:     str = ""


@dataclass
class ReadinessReport:
    run_at:    datetime
    checks:    list = field(default_factory=list)
    html_path: Optional[str] = None

    @property
    def score(self) -> float:
        return sum(c.pct for c in self.checks) / len(self.checks) if self.checks else 0.0

    @property
    def ready(self) -> bool:
        return self.score >= 80.0

    def print_summary(self):
        print(f"\nCareConnect FHIR Readiness — {self.run_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"Score: {self.score:.0f}%  ({'READY' if self.ready else 'NOT READY'} for SDoH assessments)\n")
        for c in self.checks:
            icon = "✓" if c.passed else "✗"
            print(f"  {icon} {c.name}: {c.detail}")
            if c.fix:
                print(f"    → {c.fix}")


class FHIRReadinessChecker:
    """
    Five targeted checks: is our FHIR data good enough to run SDoH assessments?

    1. Demographics — SDoH tools (PRAPARE, AHC-HRSN) need age + gender to stratify risk
    2. Recent notes — DocumentReference within 90d = active, assessable patient
    3. Coded conditions — IVG hybrid search needs SNOMED/ICD-10 to match SDoH protocols
    4. Contact points — CHW follow-up workflow needs phone/email to close the loop
    5. Recent encounter — SDoH assessment most useful when tied to a recent care visit

    LLM role: one plain-English sentence per failed check only.
    All scoring and FHIR queries are deterministic.
    """

    def __init__(self):
        self._http = httpx.Client(base_url=_FHIR_BASE, timeout=15)
        self._patients = []

    def _get(self, path, params=None):
        r = self._http.get(path, params=params or {})
        r.raise_for_status()
        return r.json()

    def _entries(self, bundle):
        return [e["resource"] for e in bundle.get("entry", [])]

    def _load_patients(self):
        self._patients = self._entries(self._get("/Patient", {"_count": _SAMPLE}))

    def _check_demographics(self):
        n, ok = len(self._patients), 0
        for p in self._patients:
            if p.get("birthDate") and p.get("gender"):
                ok += 1
        pct = ok / n * 100 if n else 0
        return Check(
            name="Patient demographics",
            passed=(pct >= 90), pct=pct,
            detail=f"{ok}/{n} patients have birthDate + gender",
        )

    def _check_recent_notes(self):
        cutoff = (datetime.now() - timedelta(days=90)).date().isoformat()
        n, ok = 0, 0
        for p in self._patients[:10]:
            n += 1
            if self._entries(self._get("/DocumentReference", {
                "patient": p["id"], "date": f"ge{cutoff}", "_count": 1,
            })):
                ok += 1
        pct = ok / n * 100 if n else 0
        return Check(
            name="Recent clinical notes (90d)",
            passed=(pct >= 70), pct=pct,
            detail=f"{ok}/{n} patients have a DocumentReference in the last 90 days",
        )

    def _check_coded_conditions(self):
        coded_systems = {
            "http://snomed.info/sct",
            "http://hl7.org/fhir/sid/icd-10",
            "http://hl7.org/fhir/sid/icd-10-cm",
        }
        total, coded = 0, 0
        for p in self._patients[:10]:
            for c in self._entries(self._get("/Condition", {
                "patient": p["id"], "clinical-status": "active", "_count": 5,
            })):
                total += 1
                if any(cd.get("system") in coded_systems
                       for cd in c.get("code", {}).get("coding", [])):
                    coded += 1
        pct = coded / total * 100 if total else 100
        return Check(
            name="Conditions coded (SNOMED/ICD-10)",
            passed=(pct >= 80), pct=pct,
            detail=f"{coded}/{total} active conditions have SNOMED or ICD-10 codes",
        )

    def _check_contact_points(self):
        n, ok = len(self._patients), 0
        for p in self._patients:
            if p.get("telecom"):
                ok += 1
        pct = ok / n * 100 if n else 0
        return Check(
            name="Patient contact points",
            passed=(pct >= 80), pct=pct,
            detail=f"{ok}/{n} patients have a phone or email (telecom) on record",
        )

    def _check_recent_encounter(self):
        cutoff = (datetime.now() - timedelta(days=365)).date().isoformat()
        n, ok = 0, 0
        for p in self._patients[:10]:
            n += 1
            if self._entries(self._get("/Encounter", {
                "patient": p["id"], "date": f"ge{cutoff}", "_count": 1,
            })):
                ok += 1
        pct = ok / n * 100 if n else 0
        return Check(
            name="Recent encounter (12 months)",
            passed=(pct >= 60), pct=pct,
            detail=f"{ok}/{n} patients have an encounter in the last 12 months",
        )

    def _add_llm_fixes(self, checks):
        failed = [c for c in checks if not c.passed]
        if not failed:
            return
        try:
            conn  = iris.connect(_IRIS_HOST, _IRIS_PORT, _IRIS_NS, _IRIS_USER, _IRIS_PASS)
            model = init_chat_model(_LLM_CONFIG, conn)
            conn.close()
        except Exception:
            return
        for c in failed:
            try:
                c.fix = model.invoke(
                    f"FHIR data quality check failed: '{c.name}' — {c.detail}\n"
                    f"One sentence: most likely cause and fix. FHIR-specific. Max 20 words."
                ).content.strip()
            except Exception:
                pass

    def _build_html(self, report, output_dir="/tmp"):
        try:
            import plotly.graph_objects as go
            import plotly.io as pio

            fig = go.Figure(go.Bar(
                x=[c.name for c in report.checks],
                y=[c.pct for c in report.checks],
                marker_color=["#008c45" if c.passed else "#dc2626" for c in report.checks],
                text=[f"{c.pct:.0f}%" for c in report.checks],
                textposition="auto",
            ))
            fig.update_layout(
                title=f"CareConnect FHIR Readiness — {report.score:.0f}% ({'READY' if report.ready else 'NOT READY'})",
                yaxis={"title": "Score (%)", "range": [0, 110]},
                shapes=[{"type": "line", "y0": 80, "y1": 80,
                         "x0": -0.5, "x1": len(report.checks) - 0.5,
                         "line": {"color": "#b45309", "dash": "dash", "width": 1.5}}],
                annotations=[{"x": len(report.checks)-1, "y": 82,
                               "text": "80% readiness threshold",
                               "showarrow": False, "font": {"color": "#b45309", "size": 11}}],
                font={"family": "DM Sans, system-ui", "size": 12},
                paper_bgcolor="#f8f9fc", plot_bgcolor="#ffffff", height=360,
            )
            rows = "".join(
                f"<tr><td class='{'ok' if c.passed else 'fail'}'>{'✓' if c.passed else '✗'}</td>"
                f"<td>{c.name}</td><td>{c.pct:.0f}%</td><td>{c.detail}</td>"
                f"<td style='color:#b45309;font-size:11px'>{c.fix}</td></tr>"
                for c in report.checks
            )
            path = f"{output_dir}/careconnect-readiness-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
            with open(path, "w") as f:
                f.write(f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>CareConnect FHIR Readiness</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&family=Fira+Code&display=swap" rel="stylesheet">
<style>body{{font-family:'DM Sans',system-ui;background:#f8f9fc;padding:32px;margin:0}}
h1{{font-size:22px;color:#0054a6;margin-bottom:4px}}
.meta{{font-family:'Fira Code',monospace;font-size:11px;color:#57606a;margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:16px}}
th{{background:#0054a6;color:#fff;padding:6px 12px;text-align:left}}
td{{padding:7px 12px;border-bottom:1px solid rgba(0,0,0,.06)}}
.ok{{color:#008c45;font-weight:700}}.fail{{color:#dc2626;font-weight:700}}</style></head><body>
<h1>CareConnect FHIR Data Readiness</h1>
<p class="meta">Run: {report.run_at.isoformat()} · Score: {report.score:.0f}%
 · {'✓ READY for SDoH assessments' if report.ready else '✗ NOT READY — fix failures first'}</p>
{pio.to_html(fig, include_plotlyjs="cdn", full_html=False)}
<table><thead><tr><th></th><th>Check</th><th>Score</th><th>Detail</th><th>Suggested fix</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>""")
            return path
        except ImportError:
            return ""

    def run(self, use_llm=True, output_dir="/tmp"):
        self._load_patients()
        report = ReadinessReport(run_at=datetime.now(), checks=[
            self._check_demographics(),
            self._check_recent_notes(),
            self._check_coded_conditions(),
            self._check_contact_points(),
            self._check_recent_encounter(),
        ])
        if use_llm:
            self._add_llm_fixes(report.checks)
        report.html_path = self._build_html(report, output_dir)
        return report


def main():
    report = FHIRReadinessChecker().run()
    report.print_summary()
    if report.html_path:
        import subprocess
        subprocess.run(["open", report.html_path])


if __name__ == "__main__":
    main()

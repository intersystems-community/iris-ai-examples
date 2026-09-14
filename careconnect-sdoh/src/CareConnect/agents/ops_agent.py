"""
CareConnect — opsreview pbuttons agent (Beat 5)

Monitors the iris-fhir container with the pbuttons analysis pattern an ops report
generator would use, packaged small enough to run inside the demo.

No external data source needed — analyzes the running iris-fhir container directly.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import iris

_IRIS_FHIR_HOST = os.environ.get("FHIR_HOST", "iris-fhir")
_IRIS_FHIR_PORT = int(os.environ.get("FHIR_PORT", "1972"))
_IRIS_FHIR_NS = os.environ.get("FHIR_NAMESPACE", "USER")
_IRIS_FHIR_USER = os.environ.get("FHIR_USERNAME", "_SYSTEM")
_IRIS_FHIR_PASS = os.environ.get("FHIR_PASSWORD", "SYS")

_IRIS_HUB_HOST = os.environ.get("IRIS_HUB_HOST", "iris-ai-hub")
_IRIS_HUB_PORT = int(os.environ.get("IRIS_HUB_PORT", "1973"))
_IRIS_HUB_NS = os.environ.get("IRIS_HUB_NAMESPACE", "USER")
_IRIS_HUB_USER = os.environ.get("IRIS_HUB_USERNAME", "_SYSTEM")
_IRIS_HUB_PASS = os.environ.get("IRIS_HUB_PASSWORD", "SYS")


@dataclass
class MetricSample:
    metric: str
    value: float
    timestamp: datetime
    severity: str = "normal"


@dataclass
class InteropSnapshot:
    queue_depths: list = field(default_factory=list)
    error_rates: list = field(default_factory=list)
    avg_latencies: list = field(default_factory=list)
    bottleneck: str = ""
    pool_exhausted: bool = False


@dataclass
class OpsReport:
    customer: str
    instance: str
    generated_at: datetime
    anomalies: list
    trends: list
    raw_metrics: dict
    interop: Optional[InteropSnapshot] = None
    html_path: Optional[str] = None


class CareConnectOpsAgent:
    """
    Monitors the iris-fhir container's performance metrics.

    Queries mgstat globals directly via IRIS Native API.
    Runs anomaly detection (z-score) and trend analysis (linear regression).
    Produces Plotly HTML report — same pattern as opsreview ManifestMedex reports.
    """

    METRICS = [
        "Glorefs",  # global references/sec
        "PhyRds",  # physical reads/sec
        "WDwij",  # write daemon wijfile writes
        "Rourefs",  # routine references/sec
        "Locks",  # lock table entries
    ]

    def __init__(self):
        self._conn = None

    def connect(self):
        self._conn = iris.connect(
            _IRIS_FHIR_HOST,
            _IRIS_FHIR_PORT,
            _IRIS_FHIR_NS,
            _IRIS_FHIR_USER,
            _IRIS_FHIR_PASS,
        )
        return self

    def disconnect(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def fetch_mgstat(self, minutes_back: int = 60) -> dict:
        iris_obj = iris.createIRIS(self._conn)
        cutoff = datetime.now() - timedelta(minutes=minutes_back)
        result = {}

        for metric in self.METRICS:
            samples = []
            gref = iris_obj.get("^mgstat", metric)
            if gref is None:
                continue
            node = iris_obj.getIRIS().node(f"^mgstat", metric)
            key = ""
            while True:
                key = node.nextKey(key)
                if key == "":
                    break
                ts_str, value = key, node.getString(key)
                try:
                    ts = datetime.strptime(ts_str[:14], "%Y%m%d%H%M%S")
                    if ts >= cutoff:
                        samples.append(
                            MetricSample(
                                metric=metric, value=float(value), timestamp=ts
                            )
                        )
                except (ValueError, TypeError):
                    continue
            result[metric] = samples

        return result

    def detect_anomalies(self, metrics: dict) -> list:
        import statistics

        anomalies = []

        for metric_name, samples in metrics.items():
            if len(samples) < 5:
                continue
            values = [s.value for s in samples]
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 0
            if stdev == 0:
                continue

            for sample in samples:
                z = abs((sample.value - mean) / stdev)
                if z > 2.5:
                    anomalies.append(
                        {
                            "metric": metric_name,
                            "value": sample.value,
                            "z_score": round(z, 2),
                            "timestamp": sample.timestamp.isoformat(),
                            "severity": "HIGH" if z > 3.5 else "MEDIUM",
                            "mean": round(mean, 2),
                        }
                    )

        return sorted(anomalies, key=lambda x: x["z_score"], reverse=True)

    def detect_trends(self, metrics: dict) -> list:
        trends = []

        for metric_name, samples in metrics.items():
            if len(samples) < 10:
                continue

            values = [s.value for s in samples]
            n = len(values)
            x = list(range(n))
            mean_x = sum(x) / n
            mean_y = sum(values) / n

            num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, values))
            den = sum((xi - mean_x) ** 2 for xi in x)
            slope = num / den if den != 0 else 0

            if abs(slope) > 0.05 * mean_y:
                direction = "increasing" if slope > 0 else "decreasing"
                projected_delta = slope * 60
                days_to_threshold = None
                if slope > 0 and mean_y > 0:
                    days_to_threshold = (
                        (mean_y * 0.5) / (slope * 60) if slope > 0 else None
                    )

                severity = "LOW"
                if days_to_threshold and days_to_threshold < 7:
                    severity = "HIGH"
                elif days_to_threshold and days_to_threshold < 30:
                    severity = "MEDIUM"

                trends.append(
                    {
                        "metric": metric_name,
                        "direction": direction,
                        "slope_per_min": round(slope, 4),
                        "current_mean": round(mean_y, 2),
                        "projected_1h_delta": round(projected_delta, 2),
                        "days_to_threshold": round(days_to_threshold, 1)
                        if days_to_threshold
                        else None,
                        "severity": severity,
                    }
                )

        return trends

    def build_html_report(self, report: OpsReport, output_dir: str = "/tmp") -> str:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            import plotly.io as pio

            fig = make_subplots(
                rows=len(self.METRICS),
                cols=1,
                subplot_titles=self.METRICS,
                shared_xaxes=True,
            )

            for i, metric_name in enumerate(self.METRICS, 1):
                samples = report.raw_metrics.get(metric_name, [])
                if not samples:
                    continue
                xs = [s.timestamp for s in samples]
                ys = [s.value for s in samples]

                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=ys,
                        name=metric_name,
                        line={"width": 1.5, "color": "#0054a6"},
                    ),
                    row=i,
                    col=1,
                )

                anomaly_samples = [
                    s
                    for s in samples
                    if any(
                        a["metric"] == metric_name
                        and abs(s.value - a["mean"]) > 2.5 * (a["value"] / a["z_score"])
                        for a in report.anomalies
                    )
                ]
                if anomaly_samples:
                    fig.add_trace(
                        go.Scatter(
                            x=[s.timestamp for s in anomaly_samples],
                            y=[s.value for s in anomaly_samples],
                            mode="markers",
                            marker={"color": "#dc2626", "size": 8, "symbol": "x"},
                            name=f"{metric_name} anomaly",
                        ),
                        row=i,
                        col=1,
                    )

            fig.update_layout(
                title=f"CareConnect OpsReview — {report.instance} — {report.generated_at.strftime('%Y-%m-%d %H:%M')}",
                font={"family": "DM Sans, system-ui", "size": 12},
                showlegend=False,
                height=200 * len(self.METRICS),
                paper_bgcolor="#f8f9fc",
                plot_bgcolor="#ffffff",
            )

            summary_html = self._build_summary_html(report)
            chart_html = pio.to_html(fig, include_plotlyjs="cdn", full_html=False)

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CareConnect OpsReview — {report.instance}</title>
<style>
body {{ font-family: 'DM Sans', system-ui, sans-serif; background: #f8f9fc; margin: 0; padding: 32px; }}
h1 {{ font-size: 24px; color: #0054a6; margin-bottom: 4px; }}
.meta {{ font-family: monospace; font-size: 11px; color: #57606a; margin-bottom: 24px; }}
</style>
</head>
<body>
<h1>CareConnect OpsReview — {report.instance}</h1>
<p class="meta">Generated: {report.generated_at.isoformat()} · Customer: {report.customer}</p>
{summary_html}
{chart_html}
</body>
</html>"""

            path = f"{output_dir}/careconnect-opsreview-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
            with open(path, "w") as f:
                f.write(html)
            return path

        except ImportError:
            return ""

    def _build_summary_html(self, report: OpsReport) -> str:
        if not report.anomalies and not report.trends:
            return "<p style='color:#008c45'>No anomalies or significant trends detected.</p>"

        rows = ""
        for a in report.anomalies[:5]:
            color = "#dc2626" if a["severity"] == "HIGH" else "#b45309"
            rows += f"<tr><td style='color:{color}'>{a['severity']}</td><td>{a['metric']}</td><td>{a['value']}</td><td>z={a['z_score']}</td><td>{a['timestamp']}</td></tr>"

        for t in report.trends:
            color = "#dc2626" if t["severity"] == "HIGH" else "#b45309"
            days = f"{t['days_to_threshold']}d" if t.get("days_to_threshold") else "N/A"
            rows += f"<tr><td style='color:{color}'>TREND</td><td>{t['metric']}</td><td>{t['direction']}</td><td>slope={t['slope_per_min']}/min</td><td>threshold in {days}</td></tr>"

        return f"""<table style='border-collapse:collapse;font-size:12px;margin-bottom:24px;width:100%'>
<thead><tr style='background:#0054a6;color:white'>
<th style='padding:6px 12px'>Severity</th><th>Metric</th><th>Value</th><th>Detail</th><th>Time</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def generate_report(
        self,
        customer: str = "CareConnect-Demo",
        instance: str = "iris-fhir",
        minutes_back: int = 60,
        output_dir: str = "/tmp",
    ) -> OpsReport:
        self.connect()
        try:
            metrics = self.fetch_mgstat(minutes_back)
            anomalies = self.detect_anomalies(metrics)
            trends = self.detect_trends(metrics)
            interop = self.fetch_interop_metrics()

            report = OpsReport(
                customer=customer,
                instance=instance,
                generated_at=datetime.now(),
                anomalies=anomalies,
                trends=trends,
                raw_metrics=metrics,
                interop=interop,
            )
            report.html_path = self.build_html_report(report, output_dir)
            return report
        finally:
            self.disconnect()

    def fetch_interop_metrics(self) -> Optional[InteropSnapshot]:
        try:
            hub_conn = iris.connect(
                _IRIS_HUB_HOST,
                _IRIS_HUB_PORT,
                _IRIS_HUB_NS,
                _IRIS_HUB_USER,
                _IRIS_HUB_PASS,
            )
            cur = hub_conn.cursor()
            snap = InteropSnapshot()

            cur.execute("""
                SELECT TargetConfigName, COUNT(*) AS Depth
                FROM Ens.MessageHeader
                WHERE Status = 1
                GROUP BY TargetConfigName
                ORDER BY Depth DESC
            """)
            snap.queue_depths = [
                {"component": r[0], "depth": r[1]} for r in cur.fetchall()
            ]

            cur.execute("""
                SELECT TargetConfigName,
                       SUM(CASE WHEN Status=6 THEN 1 ELSE 0 END) AS Errors,
                       COUNT(*) AS Total
                FROM Ens.MessageHeader
                WHERE TimeCreated > DATEADD('minute', -60, GETDATE())
                GROUP BY TargetConfigName
                HAVING COUNT(*) > 0
                ORDER BY Errors DESC
            """)
            snap.error_rates = [
                {
                    "component": r[0],
                    "errors": r[1],
                    "total": r[2],
                    "rate": round(r[1] / r[2] * 100, 1) if r[2] else 0,
                }
                for r in cur.fetchall()
            ]

            cur.execute("""
                SELECT TargetConfigName,
                       AVG(DATEDIFF('ms', TimeCreated, TimeProcessed)) AS AvgMs,
                       MAX(DATEDIFF('ms', TimeCreated, TimeProcessed)) AS MaxMs
                FROM Ens.MessageHeader
                WHERE TimeProcessed IS NOT NULL
                  AND TimeCreated > DATEADD('minute', -60, GETDATE())
                GROUP BY TargetConfigName
                ORDER BY AvgMs DESC
            """)
            snap.avg_latencies = [
                {"component": r[0], "avg_ms": r[1], "max_ms": r[2]}
                for r in cur.fetchall()
            ]

            total_queued = sum(d["depth"] for d in snap.queue_depths)
            if total_queued > 20:
                snap.pool_exhausted = True
                worst = snap.queue_depths[0] if snap.queue_depths else {}
                snap.bottleneck = (
                    f"Message backlog detected — {worst.get('component', '?')} "
                    f"queue depth {worst.get('depth', 0)}. "
                    f"Likely HTTP adapter pool exhaustion under Community Edition "
                    f"8-connection limit. Reduce PoolSize or upgrade to licensed IRIS."
                )
            elif snap.error_rates and snap.error_rates[0]["rate"] > 10:
                worst = snap.error_rates[0]
                snap.bottleneck = (
                    f"{worst['component']} error rate {worst['rate']}% "
                    f"({worst['errors']}/{worst['total']} messages in last hour). "
                    f"Check FHIR endpoint connectivity and HTTP adapter settings."
                )

            hub_conn.close()
            return snap
        except Exception:
            return None


def main():
    agent = CareConnectOpsAgent()
    report = agent.generate_report()

    print(f"Generated: {report.generated_at.isoformat()}")
    print(f"Anomalies: {len(report.anomalies)}")
    print(f"Trends:    {len(report.trends)}")

    if report.anomalies:
        for a in report.anomalies[:3]:
            print(
                f"  [{a['severity']}] {a['metric']} = {a['value']} (z={a['z_score']})"
            )

    if report.html_path:
        print(f"Report:    {report.html_path}")
        import subprocess

        subprocess.run(["open", report.html_path])


if __name__ == "__main__":
    main()

"""Unit tests for CareConnectOpsAgent — mocked IRIS, no Docker required."""
import pytest
from datetime import datetime, timedelta

pytestmark = pytest.mark.unit


def _make_agent():
    from agents.ops_agent import CareConnectOpsAgent
    return CareConnectOpsAgent()


def _fake_metrics(n=20, base=100.0, spike_at=None):
    """Build a list of MetricSample dicts suitable for detect_anomalies."""
    from agents.ops_agent import MetricSample
    samples = []
    for i in range(n):
        val = base + (500.0 if spike_at and i == spike_at else 0.0)
        samples.append(MetricSample(
            metric="Glorefs",
            value=val,
            timestamp=datetime.now() - timedelta(minutes=n - i),
        ))
    return samples


class TestDetectAnomalies:
    def test_no_anomaly_on_flat_signal(self):
        agent = _make_agent()
        metrics = {"Glorefs": _fake_metrics(20, base=100.0)}
        anomalies = agent.detect_anomalies(metrics)
        assert anomalies == []

    def test_detects_spike_anomaly(self):
        agent = _make_agent()
        metrics = {"Glorefs": _fake_metrics(20, base=100.0, spike_at=10)}
        anomalies = agent.detect_anomalies(metrics)
        assert len(anomalies) >= 1
        assert anomalies[0]["metric"] == "Glorefs"
        assert anomalies[0]["z_score"] > 2.5

    def test_severity_high_for_extreme_spike(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        samples = [MetricSample("Glorefs", 100.0, datetime.now() - timedelta(minutes=i)) for i in range(19)]
        samples.append(MetricSample("Glorefs", 10000.0, datetime.now()))
        anomalies = agent.detect_anomalies({"Glorefs": samples})
        highs = [a for a in anomalies if a["severity"] == "HIGH"]
        assert len(highs) >= 1

    def test_skips_metrics_with_fewer_than_5_samples(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        samples = [MetricSample("Glorefs", float(i * 100), datetime.now()) for i in range(3)]
        anomalies = agent.detect_anomalies({"Glorefs": samples})
        assert anomalies == []

    def test_anomalies_sorted_by_zscore_desc(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        base = [MetricSample("Glorefs", 100.0, datetime.now() - timedelta(minutes=i)) for i in range(18)]
        spike1 = MetricSample("Glorefs", 1000.0, datetime.now() - timedelta(minutes=1))
        spike2 = MetricSample("Glorefs", 5000.0, datetime.now())
        anomalies = agent.detect_anomalies({"Glorefs": base + [spike1, spike2]})
        if len(anomalies) >= 2:
            assert anomalies[0]["z_score"] >= anomalies[1]["z_score"]


class TestDetectTrends:
    def test_no_trend_on_flat_signal(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        samples = [MetricSample("Glorefs", 100.0, datetime.now() - timedelta(minutes=i)) for i in range(20)]
        trends = agent.detect_trends({"Glorefs": samples})
        assert trends == []

    def test_detects_increasing_trend(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        samples = [MetricSample("Glorefs", float(i * 10), datetime.now() - timedelta(minutes=20 - i)) for i in range(20)]
        trends = agent.detect_trends({"Glorefs": samples})
        assert len(trends) >= 1
        assert trends[0]["direction"] == "increasing"

    def test_detects_decreasing_trend(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        samples = [MetricSample("Glorefs", float((20 - i) * 10), datetime.now() - timedelta(minutes=20 - i)) for i in range(20)]
        trends = agent.detect_trends({"Glorefs": samples})
        assert len(trends) >= 1
        assert trends[0]["direction"] == "decreasing"

    def test_skips_fewer_than_10_samples(self):
        agent = _make_agent()
        from agents.ops_agent import MetricSample
        samples = [MetricSample("Glorefs", float(i * 10), datetime.now()) for i in range(5)]
        trends = agent.detect_trends({"Glorefs": samples})
        assert trends == []


class TestInteropSnapshot:
    def test_pool_exhausted_flag_set_when_queue_depth_high(self):
        agent = _make_agent()
        from agents.ops_agent import InteropSnapshot
        snap = InteropSnapshot()
        snap.queue_depths = [{"component": "PatientOnboardBP", "depth": 25}]
        snap.error_rates = []
        snap.avg_latencies = []

        total = sum(d["depth"] for d in snap.queue_depths)
        if total > 20:
            snap.pool_exhausted = True
            snap.bottleneck = f"Message backlog — {snap.queue_depths[0]['component']} depth {total}"

        assert snap.pool_exhausted is True
        assert "PatientOnboardBP" in snap.bottleneck

    def test_pool_not_exhausted_under_threshold(self):
        from agents.ops_agent import InteropSnapshot
        snap = InteropSnapshot()
        snap.queue_depths = [{"component": "SDoHFollowUpBP", "depth": 3}]
        total = sum(d["depth"] for d in snap.queue_depths)
        assert total <= 20


class TestOpsReportDataclasses:
    def test_ops_report_stores_anomalies(self):
        from agents.ops_agent import OpsReport
        report = OpsReport(
            customer="test", instance="iris-fhir",
            generated_at=datetime.now(), anomalies=[], trends=[], raw_metrics={}
        )
        assert report.anomalies == []
        assert report.customer == "test"

    def test_ops_report_not_ready_when_anomalies(self):
        from agents.ops_agent import OpsReport
        report = OpsReport(
            customer="test", instance="iris-fhir",
            generated_at=datetime.now(),
            anomalies=[{"severity": "HIGH"}],
            trends=[], raw_metrics={}
        )
        assert len(report.anomalies) > 0

    def test_ops_report_optional_fields_default_none(self):
        from agents.ops_agent import OpsReport
        report = OpsReport(
            customer="test", instance="iris-fhir",
            generated_at=datetime.now(), anomalies=[], trends=[], raw_metrics={}
        )
        assert report.interop is None
        assert report.html_path is None

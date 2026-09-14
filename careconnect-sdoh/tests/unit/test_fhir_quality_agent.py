"""Unit tests for FHIRReadinessChecker — data model only, no Docker required."""
import pytest
from datetime import datetime

pytestmark = pytest.mark.unit


class TestCheckDataclasses:
    def test_check_passed(self):
        from agents.fhir_quality_agent import Check
        c = Check(name="birthdate", passed=True, pct=100.0, detail="100% complete")
        assert c.passed is True
        assert c.pct == 100.0

    def test_check_failed_with_fix(self):
        from agents.fhir_quality_agent import Check
        c = Check(name="gender", passed=False, pct=50.0, detail="50% missing", fix="Backfill from ADT")
        assert c.passed is False
        assert c.fix == "Backfill from ADT"


class TestReadinessReport:
    def test_score_averages_checks(self):
        from agents.fhir_quality_agent import ReadinessReport, Check
        report = ReadinessReport(
            run_at=datetime.now(),
            checks=[
                Check("a", True, 100.0, "ok"),
                Check("b", False, 50.0, "partial"),
            ]
        )
        assert report.score == pytest.approx(75.0)

    def test_ready_when_score_at_or_above_80(self):
        from agents.fhir_quality_agent import ReadinessReport, Check
        report = ReadinessReport(
            run_at=datetime.now(),
            checks=[Check("a", True, 100.0, "ok"), Check("b", True, 100.0, "ok")]
        )
        assert report.ready is True

    def test_not_ready_when_score_below_80(self):
        from agents.fhir_quality_agent import ReadinessReport, Check
        report = ReadinessReport(
            run_at=datetime.now(),
            checks=[Check("a", True, 100.0, "ok"), Check("b", False, 0.0, "missing")]
        )
        assert report.ready is False

    def test_score_zero_no_checks(self):
        from agents.fhir_quality_agent import ReadinessReport
        report = ReadinessReport(run_at=datetime.now(), checks=[])
        assert report.score == 0.0

    def test_ready_false_below_threshold(self):
        from agents.fhir_quality_agent import ReadinessReport, Check
        report = ReadinessReport(
            run_at=datetime.now(),
            checks=[Check("a", False, 70.0, "partial"), Check("b", False, 75.0, "partial")]
        )
        assert report.ready is False

    def test_ready_true_at_boundary(self):
        from agents.fhir_quality_agent import ReadinessReport, Check
        report = ReadinessReport(
            run_at=datetime.now(),
            checks=[Check("a", True, 80.0, "ok")]
        )
        assert report.ready is True


class TestAgentSampleSize:
    def test_default_sample_size_is_20(self):
        from agents.fhir_quality_agent import _SAMPLE
        assert _SAMPLE == 20

    def test_checker_instantiates(self):
        from agents.fhir_quality_agent import FHIRReadinessChecker
        checker = FHIRReadinessChecker()
        assert checker is not None

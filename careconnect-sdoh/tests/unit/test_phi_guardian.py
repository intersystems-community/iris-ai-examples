"""Unit tests for phi_guardian — PHI scanning and redaction. No Docker required."""
import pytest
from pathlib import Path

from phi_guardian.src.scanner import Scanner
from phi_guardian.src.config_loader import ConfigLoader
from phi_guardian.src.redactor import Redactor

PHI_RULES = Path(__file__).resolve().parents[2] / "src/CareConnect/phi_rules.yaml"


pytestmark = pytest.mark.unit


# ── ConfigLoader ──────────────────────────────────────────────────────────────

class TestConfigLoader:
    def test_loads_global_threshold(self):
        loader = ConfigLoader(str(PHI_RULES))
        assert loader.config["global_threshold"] == 0.35

    def test_blocked_fields_present(self):
        loader = ConfigLoader(str(PHI_RULES))
        assert "patient_name" in loader.config["blocked_fields"]
        assert "ssn" in loader.config["blocked_fields"]
        assert "mrn" in loader.config["blocked_fields"]

    def test_safe_fields_present(self):
        loader = ConfigLoader(str(PHI_RULES))
        assert "sdoh_domain" in loader.config["safe_fields"]
        assert "loinc_code" in loader.config["safe_fields"]
        assert "icd10_code" in loader.config["safe_fields"]

    def test_patterns_section_has_required_keys(self):
        loader = ConfigLoader(str(PHI_RULES))
        for key in ("full_name", "phone", "email", "ssn", "mrn", "zip_code"):
            assert key in loader.config["patterns"], f"Missing pattern: {key}"

    def test_fhir_source_override_has_lower_threshold(self):
        loader = ConfigLoader(str(PHI_RULES))
        fhir_policy = loader.get_source_policy("fhir")
        assert fhir_policy["threshold"] <= 0.35

    def test_sdoh_source_override_exists(self):
        loader = ConfigLoader(str(PHI_RULES))
        policy = loader.get_source_policy("sdoh_assessment")
        assert "patient_name" in policy["blocked_fields"]

    def test_unknown_source_returns_global_defaults(self):
        loader = ConfigLoader(str(PHI_RULES))
        policy = loader.get_source_policy("nonexistent_source")
        assert policy["threshold"] == loader.config["global_threshold"]


# ── Scanner ───────────────────────────────────────────────────────────────────

class TestScanner:
    def _scanner(self):
        return Scanner(config_path=str(PHI_RULES))

    def test_detects_full_name(self):
        result = self._scanner().scan_field("body", "Patient Maria Gonzalez was seen today.")
        assert result.is_sensitive is True

    def test_detects_email(self):
        result = self._scanner().scan_field("body", "Contact: maria@example.com")
        assert result.is_sensitive is True

    def test_blocked_field_name_immediately_sensitive(self):
        # patient_name is in blocked_fields — any value in that field is sensitive
        result = self._scanner().scan_field("patient_name", "anything")
        assert result.is_sensitive is True

    def test_safe_field_name_not_flagged(self):
        # sdoh_domain is in safe_fields
        result = self._scanner().scan_field("sdoh_domain", "Economic Stability")
        assert result.is_sensitive is False

    def test_safe_loinc_code_not_flagged(self):
        result = self._scanner().scan_field("loinc_code", "88122-7")
        assert result.is_sensitive is False

    def test_empty_text_not_flagged(self):
        result = self._scanner().scan_field("body", "")
        assert result.is_sensitive is False

    def test_risk_level_not_flagged(self):
        result = self._scanner().scan_field("risk_level", "HIGH")
        assert result.is_sensitive is False

    def test_ssn_field_is_blocked(self):
        result = self._scanner().scan_field("ssn", "123-45-6789")
        assert result.is_sensitive is True

    def test_mrn_field_is_blocked(self):
        result = self._scanner().scan_field("mrn", "ABC123456")
        assert result.is_sensitive is True

    def test_phone_field_is_blocked(self):
        result = self._scanner().scan_field("phone", "(617) 555-1234")
        assert result.is_sensitive is True


# ── Redactor ──────────────────────────────────────────────────────────────────

class TestRedactor:
    def _redactor(self):
        scanner = Scanner(config_path=str(PHI_RULES))
        return Redactor(scanner=scanner)

    def test_redacts_patient_name(self):
        redactor = self._redactor()
        out = redactor.redact("Patient Maria Gonzalez was assessed today.")
        assert "Maria Gonzalez" not in out

    def test_redacts_ssn(self):
        redactor = self._redactor()
        out = redactor.redact("SSN on file: 123-45-6789")
        assert "123-45-6789" not in out

    def test_redacts_email(self):
        redactor = self._redactor()
        out = redactor.redact("Contact: patient@example.com for follow-up.")
        assert "patient@example.com" not in out

    def test_preserves_sdoh_scores(self):
        redactor = self._redactor()
        text = "Economic Stability: HIGH, Housing: MEDIUM"
        out = redactor.redact(text)
        assert "HIGH" in out
        assert "MEDIUM" in out

    def test_preserves_loinc_field(self):
        scanner = Scanner(config_path=str(PHI_RULES))
        # loinc_code is in safe_fields — never redacted regardless of value
        result = scanner.scan_field("loinc_code", "88122-7")
        assert result.is_sensitive is False

    def test_empty_text_unchanged(self):
        redactor = self._redactor()
        assert redactor.redact("") == ""

    def test_idempotent(self):
        redactor = self._redactor()
        text = "Patient John Smith was referred today."
        once = redactor.redact(text)
        twice = redactor.redact(once)
        assert once == twice

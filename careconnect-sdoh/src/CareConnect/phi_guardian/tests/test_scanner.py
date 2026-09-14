import pytest
from phi_guardian.src.scanner import Scanner

def test_scanner_detects_person():
    scanner = Scanner(entities=["PERSON"])
    result = scanner.scan_field("body", "Patient Rodrigo has a radiology issue.")
    assert result.is_sensitive is True
    assert any(e.entity_type == "PERSON" for e in result.entities)
    assert any("Rodrigo" in e.text for e in result.entities if e.text)

def test_scanner_detects_mrn():
    scanner = Scanner(entities=["MRN"])
    result = scanner.scan_field("body", "Patient with MRN123456789.")
    assert result.is_sensitive is True
    assert any(e.entity_type == "MRN" for e in result.entities)

def test_scanner_safe_text():
    scanner = Scanner(entities=["PERSON", "MRN"])
    result = scanner.scan_field("body", "The system error occurs when clicking the button.")
    assert result.is_sensitive is False
    assert result.recommended_provider == "cloud"

def test_scanner_empty_text():
    scanner = Scanner()
    result = scanner.scan_field("body", "")
    assert result.is_sensitive is False

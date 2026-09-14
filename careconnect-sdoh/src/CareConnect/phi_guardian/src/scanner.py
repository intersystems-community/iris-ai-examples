import os
import sys
from typing import List, Optional, Dict, Any
from .models import SensitivityClassification, DetectedEntity
from .config_loader import ConfigLoader

try:
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, PatternRecognizer, Pattern
    PRESIDIO_AVAILABLE = True
except ImportError:
    AnalyzerEngine = None
    RecognizerRegistry = None
    PatternRecognizer = None
    Pattern = None
    PRESIDIO_AVAILABLE = False

class Scanner:
    """Presidio-based scanner for detecting PHI and PII in text."""
    
    def __init__(self, config_path: Optional[str] = None, source_id: Optional[str] = None):
        self.config_loader = ConfigLoader(config_path)
        self.source_id = source_id
        
        if source_id:
            policy = self.config_loader.get_source_policy(source_id)
        else:
            policy = {
                "threshold": self.config_loader.config.get("global_threshold", 0.35),
                "entities": list(self.config_loader.config.get("patterns", {}).keys()),
                "patterns": self.config_loader.config.get("patterns", {})
            }
            
        self.threshold = policy.get("threshold", 0.35)
        self.entities = list(policy.get("patterns", {}).keys()) or ["PERSON", "EMAIL_ADDRESS", "LOCATION", "MRN", "COMPANY"]
            
        self.analyzer = None
        if PRESIDIO_AVAILABLE:
            try:
                # Initialize Presidio Analyzer
                registry = RecognizerRegistry()
                registry.load_predefined_recognizers()
                
                # Add custom patterns from config
                for name, pattern_str in policy.get("patterns", {}).items():
                    pattern = Pattern(name=f"{name}_pattern", regex=pattern_str, score=0.5)
                    recognizer = PatternRecognizer(supported_entity=name.upper(), patterns=[pattern])
                    registry.add_recognizer(recognizer)
                    if name.upper() not in self.entities:
                        self.entities.append(name.upper())
                
                self.analyzer = AnalyzerEngine(registry=registry, default_score_threshold=self.threshold)
            except (Exception, SystemExit):
                self.analyzer = None

    def scan_field(self, field_name: str, text: str) -> SensitivityClassification:
        """Scans a single field for sensitive information."""
        policy = self.config_loader.get_source_policy(self.source_id or "default")
        blocked_fields = policy.get("blocked_fields", [])
        safe_fields = policy.get("safe_fields", [])

        # 1. Check if explicitly blocked
        if field_name in blocked_fields:
            return SensitivityClassification(
                field_name=field_name,
                is_sensitive=True,
                entities=[DetectedEntity(entity_type="BLOCKED_FIELD", start_index=0, end_index=0, score=1.0, text="N/A")],
                recommended_provider="local"
            )

        # 2. Check if explicitly safe
        if field_name in safe_fields:
            return SensitivityClassification(
                field_name=field_name,
                is_sensitive=False,
                entities=[],
                recommended_provider="cloud"
            )

        if not text or not self.analyzer:
            return SensitivityClassification(
                field_name=field_name,
                is_sensitive=False,
                entities=[],
                recommended_provider="cloud"
            )
            
        try:
            results = self.analyzer.analyze(text=text, entities=self.entities, language="en")
            
            detected_entities = [
                DetectedEntity(
                    entity_type=res.entity_type,
                    start_index=res.start,
                    end_index=res.end,
                    score=res.score,
                    text=text[res.start:res.end]
                )
                for res in results
            ]
            
            is_sensitive = len(detected_entities) > 0
            recommended_provider = "local" if is_sensitive else "cloud"
            
            return SensitivityClassification(
                field_name=field_name,
                is_sensitive=is_sensitive,
                entities=detected_entities,
                recommended_provider=recommended_provider
            )
        except Exception:
            return SensitivityClassification(
                field_name=field_name,
                is_sensitive=False,
                entities=[],
                recommended_provider="cloud"
            )

    def scan_ticket(self, fields: dict) -> List[SensitivityClassification]:
        """Scans multiple fields of a ticket."""
        return [self.scan_field(name, val) for name, val in fields.items() if isinstance(val, str)]

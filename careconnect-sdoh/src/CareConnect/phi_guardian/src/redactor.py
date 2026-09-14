from presidio_anonymizer import AnonymizerEngine
from .scanner import Scanner
from typing import List, Optional

class Redactor:
    """Presidio-based redactor for scrubbing sensitive information."""
    
    def __init__(self, scanner: Optional[Scanner] = None):
        self.scanner = scanner or Scanner()
        self.engine = AnonymizerEngine()

    def redact(self, text: str) -> str:
        """Redacts sensitive entities from text."""
        if not text:
            return text
            
        # Scan for entities
        scan_result = self.scanner.scan_field("text", text)
        
        if not scan_result.entities:
            return text
            
        # Convert our models to Presidio's expected format for anonymization
        # Note: AnonymizerEngine usually expects Analyzer results directly, 
        # but we can also pass a list of dicts if we follow their schema.
        from presidio_analyzer import AnalyzerEngine
        # To keep it simple and reliable, we'll re-run analyzer via the scanner's instance
        analyzer_results = self.scanner.analyzer.analyze(
            text=text, 
            entities=self.scanner.entities, 
            language="en"
        )
        
        anonymized_result = self.engine.anonymize(
            text=text,
            analyzer_results=analyzer_results
        )
        
        return anonymized_result.text

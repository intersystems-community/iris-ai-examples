from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

class DetectedEntity(BaseModel):
    """Represents a specific sensitive entity identified by the scanner."""
    entity_type: str = Field(..., description="Type of entity (e.g., 'PERSON', 'MRN', 'COMPANY')")
    start_index: int = Field(..., description="Character offset of the start of the entity")
    end_index: int = Field(..., description="Character offset of the end of the entity")
    score: float = Field(..., description="Confidence score of the detection")
    text: Optional[str] = Field(None, description="The actual text of the entity (if available)")

class SensitivityClassification(BaseModel):
    """Represents the results of PHI/PII detection for a specific field."""
    field_name: str = Field(..., description="The name of the field (e.g., 'title', 'body')")
    is_sensitive: bool = Field(..., description="Whether PHI/PII was detected in this field")
    entities: List[DetectedEntity] = Field(default_factory=list, description="List of specific sensitive entities found")
    recommended_provider: str = Field(..., description="Recommended LLM provider type ('local' or 'cloud')")

class RoutingAuditLog(BaseModel):
    """Persistence for auditing routing decisions."""
    ticket_id: str = Field(..., description="The identifier of the ticket")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the routing decision was made")
    field_routings: Dict[str, str] = Field(..., description="Map of field_name to provider_id")
    total_latency_ms: float = Field(0.0, description="Overhead introduced by the routing logic")

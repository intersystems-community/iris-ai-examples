import pytest
import yaml
from pathlib import Path
from packages.phi_guardian.src.config_loader import ConfigLoader

def test_config_loader_parity():
    """Verifies that the ConfigLoader correctly reads the shared phi_rules.yaml."""
    config_path = Path(__file__).parent.parent.parent.parent / "phi_rules.yaml"
    assert config_path.exists()
    
    loader = ConfigLoader(str(config_path))
    
    # Verify global settings
    assert loader.config["global_threshold"] == 0.35
    assert "ticket_id" in loader.config["safe_fields"]
    assert "customer_name" in loader.config["blocked_fields"]
    
    # Verify patterns
    assert "mrn" in loader.config["patterns"]
    
    # Verify source overrides
    solr_policy = loader.get_source_policy("solr")
    assert solr_policy["threshold"] == 0.4
    assert "internal_notes" in solr_policy["blocked_fields"]
    assert "customer_name" in solr_policy["blocked_fields"]

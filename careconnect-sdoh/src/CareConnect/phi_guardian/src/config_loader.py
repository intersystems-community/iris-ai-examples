import yaml
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

class ConfigLoader:
    """Loader for the shared PHI/PII security configuration."""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self.path = Path(config_path)
        else:
            # Default to root of the repo (one level up from packages/)
            self.path = Path(__file__).parent.parent.parent.parent / "phi_rules.yaml"
            
        self.config: Dict[str, Any] = {}
        self.load()

    def load(self):
        """Loads and parses the YAML configuration."""
        if not self.path.exists():
            print(f"⚠️ Security config not found at {self.path}. Using empty defaults.")
            self.config = {
                "global_threshold": 0.35,
                "safe_fields": [],
                "blocked_fields": [],
                "patterns": {},
                "sources": {}
            }
            return

        with open(self.path, 'r') as f:
            self.config = yaml.safe_load(f)

    def get_source_policy(self, source_id: str) -> Dict[str, Any]:
        """Returns the specific policy for a data source, merged with globals."""
        source_config = self.config.get("sources", {}).get(source_id, {})
        
        return {
            "threshold": source_config.get("threshold", self.config.get("global_threshold", 0.35)),
            "blocked_fields": list(set(self.config.get("blocked_fields", []) + source_config.get("blocked_fields", []))),
            "safe_fields": self.config.get("safe_fields", []),
            "patterns": self.config.get("patterns", {})
        }

    def get_all_patterns(self) -> Dict[str, str]:
        """Returns all configured regex patterns."""
        return self.config.get("patterns", {})

"""``python -m aihub_service.openapi > openapi.json`` — print the HTTP contract.

The routes do not depend on the config, so the offline CareConnect config is
used to build the app; tests/test_api.py fails when the file is stale.
"""

import json
from pathlib import Path

from .app import create_app

if __name__ == "__main__":
    here = Path(__file__).resolve().parents[2]
    app = create_app(here / "examples" / "careconnect" / "offline.yaml")
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))

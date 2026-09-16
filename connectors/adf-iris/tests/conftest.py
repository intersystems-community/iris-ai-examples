import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA_SUBSET_PATH = ROOT / "schemas" / "adf-schema-subset.json"


@pytest.fixture(scope="session")
def schema_subset() -> dict:
    return json.loads(SCHEMA_SUBSET_PATH.read_text())


@pytest.fixture()
def sample_config():
    from generator import IrisConnectionConfig

    return IrisConnectionConfig(
        host="iris.example.internal",
        username="adf_reader",
        key_vault_secret_name="iris-adf-reader-pwd",
    )


@pytest.fixture()
def sample_bundle(sample_config):
    from generator import generate_bundle

    return generate_bundle(
        sample_config,
        tables=["SQLUser.Patient", "Epic.Encounter"],
        factory_name="adf-iris-demo",
        key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
        storage_container="iris-export",
        storage_connection_string_secret_name="blob-conn-string",
    )

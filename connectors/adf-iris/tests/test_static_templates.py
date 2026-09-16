"""Validate the hand-authored, parameterized ARM templates in ../templates/
-- not just the generator's output. These are what a human deploys directly
with `az deployment group create --template-file ... --parameters ...`.

Values here are ARM expressions like "[parameters('irisHost')]" rather than
literals. That's fine against the real schema: none of the Odbc/AzureBlob/
AzureKeyVault typeProperties fields we use are declared with a plain
"type": "string" in the schema (only a free-text "description"), so any
JSON value -- including a bracket-expression string -- passes. Fields that
*are* strictly typed (the linked-service "type" enum, the SecretBase
"type" enum, LinkedServiceReference's required keys) are checked because we
never parameterize those away.
"""
import json
from pathlib import Path

import pytest

from schema_validation_helper import assert_valid

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

TEMPLATE_DEF_MAP = {
    "linked-service-keyvault.json": "LinkedService",
    "linked-service-iris-odbc.json": "LinkedService",
    "linked-service-blob-storage.json": "LinkedService",
    "dataset-iris-odbc-table.json": "Dataset",
    "dataset-blob-delimited-text.json": "Dataset",
}


@pytest.mark.parametrize("filename", sorted(p.name for p in TEMPLATES_DIR.glob("*.json")))
def test_template_is_valid_json_with_arm_envelope(filename):
    doc = json.loads((TEMPLATES_DIR / filename).read_text())
    assert doc["$schema"].startswith("https://schema.management.azure.com/schemas/")
    assert doc["contentVersion"] == "1.0.0.0"
    assert isinstance(doc["resources"], list) and len(doc["resources"]) == 1
    resource = doc["resources"][0]
    assert resource["apiVersion"] == "2018-06-01"
    assert resource["type"].startswith("Microsoft.DataFactory/factories/")


@pytest.mark.parametrize("filename,def_name", sorted(TEMPLATE_DEF_MAP.items()))
def test_template_properties_match_real_schema(schema_subset, filename, def_name):
    doc = json.loads((TEMPLATES_DIR / filename).read_text())
    properties = doc["resources"][0]["properties"]
    assert_valid(schema_subset, def_name, properties)


def test_self_hosted_ir_template_matches_schema(schema_subset):
    doc = json.loads((TEMPLATES_DIR / "self-hosted-integration-runtime.json").read_text())
    properties = doc["resources"][0]["properties"]
    assert_valid(schema_subset, "IntegrationRuntime", properties)


def test_pipeline_template_activity_matches_schema(schema_subset):
    doc = json.loads((TEMPLATES_DIR / "pipeline-copy-iris-to-blob.json").read_text())
    activity = doc["resources"][0]["properties"]["activities"][0]
    assert_valid(schema_subset, "Activity", activity)
    assert activity["typeProperties"]["source"]["type"] == "OdbcSource"
    assert activity["typeProperties"]["sink"]["type"] == "DelimitedTextSink"


def test_resource_names_use_concat_expression_not_a_literal_slash():
    """The static templates target an *existing* factory, so they use the
    "[concat(parameters('factoryName'), '/', ...)]" ARM idiom rather than
    the generator's nesting approach. Confirm every resource name is an ARM
    expression (starts with '[') rather than a literal string containing a
    raw '/', which the real schema's name pattern rejects for literals."""
    for path in TEMPLATES_DIR.glob("*.json"):
        doc = json.loads(path.read_text())
        for resource in doc["resources"]:
            name = resource["name"]
            assert name.startswith("[") and name.endswith("]"), (path.name, name)


def test_no_password_or_connection_secret_is_inlined_in_any_static_template():
    for path in TEMPLATES_DIR.glob("*.json"):
        text = path.read_text()
        assert '"type": "SecureString"' not in text, f"{path.name} inlines a SecureString"
        assert "PWD=" not in text

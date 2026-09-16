"""
Validates the connector's spec.yaml two ways:

1. Through the CDK's own `BaseConnector.spec()` / `ConnectorSpecificationSerializer`
   (the exact code path `AirbyteEntrypoint` runs in production), which is the CDK's
   own validation entrypoint and works fully offline.
2. Through the general-purpose `jsonschema` library's Draft-07 meta-schema validator,
   confirming `connectionSpecification` is itself a syntactically valid JSON Schema
   (not just a dict the CDK's dataclass loader happens to accept).
"""

import json
import logging

import jsonschema
from airbyte_cdk.models import ConnectorSpecificationSerializer

from source_iris.source import IrisSource

logger = logging.getLogger("test")


def test_spec_loads_via_cdk_base_connector_spec_method():
    source = IrisSource(connection_factory=lambda config: None)
    spec = source.spec(logger)  # BaseConnector.spec() — reads source_iris/spec.yaml
    assert spec.connectionSpecification["title"] == "InterSystems IRIS Source Spec"
    assert "password" in spec.connectionSpecification["properties"]


def test_spec_password_field_is_marked_as_airbyte_secret():
    source = IrisSource(connection_factory=lambda config: None)
    spec = source.spec(logger)
    assert spec.connectionSpecification["properties"]["password"]["airbyte_secret"] is True


def test_spec_required_fields_present():
    source = IrisSource(connection_factory=lambda config: None)
    spec = source.spec(logger)
    required = set(spec.connectionSpecification["required"])
    assert required == {"host", "port", "namespace", "username", "password"}


def test_spec_round_trips_through_connector_specification_serializer():
    # Belt-and-suspenders: reload the raw spec.yaml as a plain dict and push it back
    # through the CDK's own serializer, the same object AirbyteEntrypoint constructs
    # a SPEC AirbyteMessage from.
    import yaml
    from importlib import resources

    raw = resources.files("source_iris").joinpath("spec.yaml").read_text()
    spec_dict = yaml.safe_load(raw)
    loaded = ConnectorSpecificationSerializer.load(spec_dict)
    assert loaded.connectionSpecification == spec_dict["connectionSpecification"]


def test_connection_specification_is_a_valid_draft7_json_schema():
    source = IrisSource(connection_factory=lambda config: None)
    spec = source.spec(logger)
    jsonschema.Draft7Validator.check_schema(spec.connectionSpecification)


def test_valid_config_validates_against_connection_specification():
    source = IrisSource(connection_factory=lambda config: None)
    spec = source.spec(logger)
    valid_config = {
        "host": "localhost",
        "port": 1972,
        "namespace": "USER",
        "username": "_SYSTEM",
        "password": "SYS",
    }
    jsonschema.validate(valid_config, spec.connectionSpecification)


def test_config_missing_required_field_fails_validation():
    source = IrisSource(connection_factory=lambda config: None)
    spec = source.spec(logger)
    invalid_config = {"host": "localhost", "port": 1972, "namespace": "USER", "username": "_SYSTEM"}  # no password
    import pytest

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid_config, spec.connectionSpecification)


def test_spec_via_airbyte_entrypoint_cli():
    """Runs the real CDK CLI entrypoint's `spec` command end to end, offline."""
    from airbyte_cdk.entrypoint import AirbyteEntrypoint

    source = IrisSource(connection_factory=lambda config: None)
    entrypoint = AirbyteEntrypoint(source)
    parsed = entrypoint.parse_args(["spec"])
    messages = [json.loads(m) for m in entrypoint.run(parsed) if m.strip()]
    spec_messages = [m for m in messages if m.get("type") == "SPEC"]
    assert len(spec_messages) == 1
    assert spec_messages[0]["spec"]["connectionSpecification"]["title"] == "InterSystems IRIS Source Spec"

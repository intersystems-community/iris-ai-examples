"""Round-trip and structural tests for the generator output."""
import json

import pytest

from generator import IrisConnectionConfig, generate_bundle, wrap_arm_template


def _cfg():
    return IrisConnectionConfig(
        host="iris-prod.internal",
        username="adf_reader",
        key_vault_secret_name="iris-adf-reader-pwd",
    )


def test_generate_bundle_is_deterministic():
    """Same inputs -> byte-identical JSON. A generator whose output drifts
    between runs (dict ordering, random IDs, timestamps) would silently
    break CI diffing and code review of the generated templates."""
    kwargs = dict(
        config=_cfg(),
        tables=["SQLUser.Patient", "Epic.Encounter"],
        factory_name="adf-iris-demo",
        key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
        storage_container="iris-export",
        storage_connection_string_secret_name="blob-conn-string",
    )
    first = json.dumps(generate_bundle(**kwargs)["template"], sort_keys=True)
    second = json.dumps(generate_bundle(**kwargs)["template"], sort_keys=True)
    assert first == second


def test_generate_bundle_is_json_serializable_round_trip():
    bundle = generate_bundle(
        _cfg(),
        tables=["SQLUser.Patient"],
        factory_name="adf-iris-demo",
        key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
        storage_container="iris-export",
        storage_connection_string_secret_name="blob-conn-string",
    )
    text = json.dumps(bundle["template"])
    restored = json.loads(text)
    assert restored == bundle["template"]


def test_one_resource_set_per_table():
    tables = ["SQLUser.Patient", "SQLUser.Encounter", "HSFHIR.Observation"]
    bundle = generate_bundle(
        _cfg(),
        tables=tables,
        factory_name="adf-iris-demo",
        key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
        storage_container="iris-export",
        storage_connection_string_secret_name="blob-conn-string",
    )
    assert set(bundle["datasets"].keys()) == set(tables)
    assert set(bundle["pipelines"].keys()) == set(tables)
    for table in tables:
        query = bundle["pipelines"][table]["properties"]["activities"][0]["typeProperties"]["source"]["query"]
        assert table in query


def test_empty_table_list_rejected():
    with pytest.raises(ValueError):
        generate_bundle(
            _cfg(),
            tables=[],
            factory_name="adf-iris-demo",
            key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
            storage_container="iris-export",
            storage_connection_string_secret_name="blob-conn-string",
        )


def test_dataset_names_are_unique_for_normal_table_lists():
    tables = ["SQLUser.Patient", "SQLUser.Encounter", "HSFHIR.Observation"]
    bundle = generate_bundle(
        _cfg(),
        tables=tables,
        factory_name="adf-iris-demo",
        key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
        storage_container="iris-export",
        storage_connection_string_secret_name="blob-conn-string",
    )
    names = [bundle["datasets"][t]["source"]["name"] for t in tables]
    assert len(names) == len(set(names)), f"dataset name collision: {names}"


def test_colliding_sanitized_names_raise_a_clear_error_instead_of_silently_overwriting():
    """'SQLUser.Patient' and 'SQLUser_Patient' both sanitize to
    'SQLUser_Patient' (ADF resource names can't contain '.'). Silently
    generating two resources with the same name would mean the second
    definition silently clobbers the first in the emitted template --
    this must be a loud, explicit error instead."""
    with pytest.raises(ValueError, match="collide"):
        generate_bundle(
            _cfg(),
            tables=["SQLUser.Patient", "SQLUser_Patient"],
            factory_name="adf-iris-demo",
            key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
            storage_container="iris-export",
            storage_connection_string_secret_name="blob-conn-string",
        )


def test_no_resource_name_contains_a_slash():
    """Regression pin for the schema-invalidating bug described in
    generate_adf_templates._factory_resource's docstring."""
    bundle = generate_bundle(
        _cfg(),
        tables=["SQLUser.Patient"],
        factory_name="adf-iris-demo",
        key_vault_base_url="https://kv-iris-demo.vault.azure.net/",
        storage_container="iris-export",
        storage_connection_string_secret_name="blob-conn-string",
    )
    factory_resource = bundle["template"]["resources"][0]
    for child in factory_resource["resources"]:
        assert "/" not in child["name"], child["name"]


def test_wrap_arm_template_top_level_shape():
    template = wrap_arm_template([], factory_name="f")
    assert template["$schema"].startswith("https://schema.management.azure.com/schemas/")
    assert template["contentVersion"] == "1.0.0.0"
    assert isinstance(template["resources"], list)

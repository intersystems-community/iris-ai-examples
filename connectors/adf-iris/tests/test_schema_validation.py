"""Validate generated ARM fragments against the real, vendored
Microsoft.DataFactory ARM schema (see schemas/adf-schema-subset.json and
schemas/build_schema_subset.py for provenance).

This is real jsonschema Draft-04 validation against Microsoft's own schema
definitions -- not a hand-rolled structural check -- for every piece this
generator emits: the Odbc/AzureBlobStorage/AzureKeyVault linked services,
the OdbcTable/DelimitedText datasets, the OdbcSource/DelimitedTextSink copy
activity, and the self-hosted integration runtime. It also validates the
full ARM resource wrapper (name/type/apiVersion/properties) via
resourceDefinitions, which is what caught the "integrationruntimes" casing
bug and the "factoryName/childName" name-pattern bug during development.
"""
from schema_validation_helper import assert_resource_valid, assert_valid


def test_iris_linked_service_matches_odbc_schema(schema_subset, sample_bundle):
    assert_valid(schema_subset, "LinkedService", sample_bundle["iris_linked_service"]["properties"])


def test_iris_linked_service_resource_wrapper_valid(schema_subset, sample_bundle):
    assert_resource_valid(
        schema_subset, "factories_linkedservices", sample_bundle["iris_linked_service"]
    )


def test_keyvault_linked_service_matches_schema(schema_subset, sample_bundle):
    assert_valid(schema_subset, "LinkedService", sample_bundle["keyvault_linked_service"]["properties"])
    assert_resource_valid(
        schema_subset, "factories_linkedservices", sample_bundle["keyvault_linked_service"]
    )


def test_blob_linked_service_matches_schema(schema_subset, sample_bundle):
    assert_valid(schema_subset, "LinkedService", sample_bundle["blob_linked_service"]["properties"])
    assert_resource_valid(
        schema_subset, "factories_linkedservices", sample_bundle["blob_linked_service"]
    )


def test_self_hosted_ir_matches_schema(schema_subset, sample_bundle):
    assert_valid(schema_subset, "IntegrationRuntime", sample_bundle["self_hosted_ir"]["properties"])
    assert_resource_valid(
        schema_subset, "factories_integrationRuntimes", sample_bundle["self_hosted_ir"]
    )


def test_datasets_match_schema(schema_subset, sample_bundle):
    for pair in sample_bundle["datasets"].values():
        assert_valid(schema_subset, "Dataset", pair["source"]["properties"])
        assert_resource_valid(schema_subset, "factories_datasets", pair["source"])
        assert_valid(schema_subset, "Dataset", pair["sink"]["properties"])
        assert_resource_valid(schema_subset, "factories_datasets", pair["sink"])


def test_pipelines_match_schema(schema_subset, sample_bundle):
    for pipeline in sample_bundle["pipelines"].values():
        for activity in pipeline["properties"]["activities"]:
            assert_valid(schema_subset, "Activity", activity)
        assert_resource_valid(schema_subset, "factories_pipelines", pipeline)


def test_copy_activity_source_and_sink_match_schema(schema_subset, sample_bundle):
    for pipeline in sample_bundle["pipelines"].values():
        activity = pipeline["properties"]["activities"][0]
        source = activity["typeProperties"]["source"]
        sink = activity["typeProperties"]["sink"]
        assert_valid(schema_subset, "CopySource", source)
        assert_valid(schema_subset, "CopySink", sink)
        assert source["type"] == "OdbcSource"


def test_full_template_resources_all_validate(schema_subset, sample_bundle):
    """Walk the actual nested ARM template (what a human would `az deployment
    group create` with) rather than just the individually-returned dicts, to
    make sure nesting didn't change anything."""
    factory_resource = sample_bundle["template"]["resources"][0]
    assert factory_resource["type"] == "Microsoft.DataFactory/factories"
    children_by_type = {}
    for child in factory_resource["resources"]:
        children_by_type.setdefault(child["type"], []).append(child)

    for ls in children_by_type["Microsoft.DataFactory/factories/linkedservices"]:
        assert_resource_valid(schema_subset, "factories_linkedservices", ls)
        assert_valid(schema_subset, "LinkedService", ls["properties"])

    for ds in children_by_type["Microsoft.DataFactory/factories/datasets"]:
        assert_resource_valid(schema_subset, "factories_datasets", ds)
        assert_valid(schema_subset, "Dataset", ds["properties"])

    for pl in children_by_type["Microsoft.DataFactory/factories/pipelines"]:
        assert_resource_valid(schema_subset, "factories_pipelines", pl)

    for ir in children_by_type["Microsoft.DataFactory/factories/integrationRuntimes"]:
        assert_resource_valid(schema_subset, "factories_integrationRuntimes", ir)


def test_wrong_type_name_is_rejected(schema_subset):
    """Sanity check that the validator actually has teeth (a schema that
    accepts everything would make the tests above meaningless)."""
    bogus = {"type": "Snowflake", "typeProperties": {"account": "x"}}
    try:
        assert_valid(schema_subset, "LinkedService", bogus)
    except AssertionError:
        return
    raise AssertionError("expected a bogus linked-service type to be rejected")


def test_missing_required_connection_string_is_rejected(schema_subset):
    bogus = {"type": "Odbc", "typeProperties": {"authenticationType": "Basic"}}
    try:
        assert_valid(schema_subset, "LinkedService", bogus)
    except AssertionError:
        return
    raise AssertionError("expected a missing connectionString to be rejected")


def test_slash_in_literal_resource_name_is_rejected_by_real_schema(schema_subset, sample_bundle):
    """Documents the exact bug this generator used to have: a literal
    (non-ARM-expression) resource name containing '/' fails the real
    schema's name pattern. If this ever stops raising, the schema subset
    was regenerated incorrectly."""
    bad_resource = dict(sample_bundle["iris_linked_service"])
    bad_resource["name"] = "adf-iris-demo/IrisOdbcLinkedService"
    try:
        assert_resource_valid(schema_subset, "factories_linkedservices", bad_resource)
    except AssertionError:
        return
    raise AssertionError("expected a slash-containing literal name to be rejected")

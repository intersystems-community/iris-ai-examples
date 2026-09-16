#!/usr/bin/env python3
"""Build schemas/adf-schema-subset.json from the vendored, real Microsoft
ARM schema for Microsoft.DataFactory.

This is NOT a hand-written schema. Every definition in the output file is a
verbatim copy of a node from the official schema files fetched from:

  https://raw.githubusercontent.com/Azure/azure-resource-manager-schemas/master/schemas/2018-06-01/Microsoft.DataFactory.json
  https://raw.githubusercontent.com/Azure/azure-resource-manager-schemas/master/schemas/common/definitions.json

(the same schema store Azure Resource Manager / VS Code ARM tooling use).
Those two files are vendored unmodified in ../vendor/.

We only *select* which oneOf branches to keep, because the full LinkedService
/ Dataset / CopySource / CopySink / Activity unions each have 100-400+
branches (one per connector Microsoft ships) and pulling in all of them would
make the offline test fixture enormous and unrelated to IRIS. Every branch we
keep is copied byte-for-byte from the source file -- nothing is retyped by
hand. Run this script again any time the vendored schema is refreshed.

Usage:
    python3 build_schema_subset.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE.parent / "vendor"
SOURCE_SCHEMA = VENDOR / "Microsoft.DataFactory.2018-06-01.json"
SOURCE_COMMON = VENDOR / "arm-common-definitions.json"
OUT_PATH = HERE / "adf-schema-subset.json"

SOURCE_URL = (
    "https://raw.githubusercontent.com/Azure/azure-resource-manager-schemas/"
    "master/schemas/2018-06-01/Microsoft.DataFactory.json"
)
COMMON_URL = (
    "https://raw.githubusercontent.com/Azure/azure-resource-manager-schemas/"
    "master/schemas/common/definitions.json"
)


def branch(union: dict, type_name: str) -> dict:
    """Pull one 'oneOf' branch (identified by its type enum) out of a union
    definition, verbatim."""
    for opt in union["oneOf"]:
        enum = opt.get("properties", {}).get("type", {}).get("enum", [None])
        if enum and enum[0] == type_name:
            return copy.deepcopy(opt)
    raise KeyError(f"branch {type_name!r} not found")


def main() -> None:
    schema = json.loads(SOURCE_SCHEMA.read_text())
    defs = schema["definitions"]
    rdefs = schema["resourceDefinitions"]

    out_defs = {}

    # Plain, non-union definitions copied verbatim.
    for name in [
        "SecretBase",
        "SecureString",
        "AzureKeyVaultSecretReference",
        "LinkedServiceReference",
        "IntegrationRuntimeReference",
        "DatasetReference",
        "CredentialReference",
        "OdbcLinkedServiceTypeProperties",
        "AzureBlobStorageLinkedServiceTypeProperties",
        "AzureKeyVaultLinkedServiceTypeProperties",
        "OdbcTableDatasetTypeProperties",
        "DelimitedTextDatasetTypeProperties",
        "CopyActivityTypeProperties",
        "ActivityPolicy",
        "Pipeline",
        "SelfHostedIntegrationRuntimeTypeProperties",
    ]:
        out_defs[name] = copy.deepcopy(defs[name])

    # Unions trimmed to the branches this generator actually emits. Each
    # branch is copied verbatim; only sibling branches for connectors we
    # don't use (Snowflake, SAP, Salesforce, ...) are dropped.
    out_defs["LinkedService"] = {
        "description": defs["LinkedService"]["description"],
        "oneOf": [
            branch(defs["LinkedService"], "Odbc"),
            branch(defs["LinkedService"], "AzureBlobStorage"),
            branch(defs["LinkedService"], "AzureKeyVault"),
        ],
    }
    out_defs["Dataset"] = {
        "description": defs["Dataset"]["description"],
        "oneOf": [
            branch(defs["Dataset"], "OdbcTable"),
            branch(defs["Dataset"], "DelimitedText"),
        ],
    }
    out_defs["CopySource"] = {
        "description": defs["CopySource"]["description"],
        "oneOf": [branch(defs["CopySource"], "OdbcSource")],
    }
    out_defs["CopySink"] = {
        "description": defs["CopySink"]["description"],
        "oneOf": [
            branch(defs["CopySink"], "BlobSink"),
            branch(defs["CopySink"], "DelimitedTextSink"),
        ],
    }
    out_defs["Activity"] = {
        "description": defs["Activity"]["description"],
        "oneOf": [branch(defs["Activity"], "Copy")],
    }
    out_defs["IntegrationRuntime"] = {
        "description": defs["IntegrationRuntime"]["description"],
        "oneOf": [branch(defs["IntegrationRuntime"], "SelfHosted")],
    }
    out_defs["DatasetLocation"] = {
        "description": defs["DatasetLocation"]["description"],
        "oneOf": [branch(defs["DatasetLocation"], "AzureBlobStorageLocation")],
    }

    out_rdefs = {
        name: copy.deepcopy(rdefs[name])
        for name in [
            "factories_linkedservices",
            "factories_datasets",
            "factories_pipelines",
            "factories_integrationRuntimes",
        ]
    }

    common = json.loads(SOURCE_COMMON.read_text())

    output = {
        "_provenance": {
            "note": (
                "Trimmed, verbatim subset of the official Azure Resource "
                "Manager schema for Microsoft.DataFactory. Generated by "
                "build_schema_subset.py -- do not hand-edit. Every "
                "definition below is copied byte-for-byte from the source "
                "file; only unrelated sibling oneOf branches (other "
                "connectors' linked services/datasets/sources/sinks) were "
                "removed to keep this fixture small."
            ),
            "source_schema_url": SOURCE_URL,
            "common_definitions_url": COMMON_URL,
            "vendored_copies": [
                str(SOURCE_SCHEMA.relative_to(HERE.parent)),
                str(SOURCE_COMMON.relative_to(HERE.parent)),
            ],
        },
        "definitions": out_defs,
        "resourceDefinitions": out_rdefs,
        # Needed so jsonschema's RefResolver can resolve the many
        # "https://schema.management.azure.com/schemas/common/definitions.json#/definitions/expression"
        # $refs offline, with the real file content (not a stub).
        "common_definitions": common,
    }

    OUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

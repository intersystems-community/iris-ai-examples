"""Shared helper for validating generated ARM fragments against the real,
vendored Microsoft.DataFactory ARM schema subset (see ../schemas/).

Uses jsonschema's (deprecated but still functional in 4.26) RefResolver so
the many external $refs to
https://schema.management.azure.com/schemas/common/definitions.json#/...
resolve offline against the vendored copy of that file, instead of hitting
the network or being stubbed out.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import jsonschema
from jsonschema.validators import Draft4Validator

ROOT = Path(__file__).resolve().parent.parent
COMMON_URL = "https://schema.management.azure.com/schemas/common/definitions.json"


def make_validator(schema_subset: dict, def_name: str) -> Draft4Validator:
    schema = {
        "definitions": schema_subset["definitions"],
        "$ref": f"#/definitions/{def_name}",
    }
    store = {COMMON_URL: schema_subset["common_definitions"]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        resolver = jsonschema.RefResolver.from_schema(schema, store=store)
        return Draft4Validator(schema, resolver=resolver)


def assert_valid(schema_subset: dict, def_name: str, instance: dict) -> None:
    validator = make_validator(schema_subset, def_name)
    errors = list(validator.iter_errors(instance))
    if errors:
        formatted = "\n".join(f"  - {'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors)
        raise AssertionError(
            f"{instance.get('type', instance)!r} did not validate against "
            f"definitions/{def_name} (real Microsoft ARM schema):\n{formatted}"
        )


def make_resource_validator(schema_subset: dict, resource_def_name: str) -> Draft4Validator:
    """Validate a full ARM *resource* entry (type/apiVersion/name/properties
    wrapper), e.g. resourceDefinitions/factories_linkedservices."""
    schema = {
        "definitions": schema_subset["definitions"],
        "$ref": f"#/resourceDefinitions/{resource_def_name}",
        "resourceDefinitions": schema_subset["resourceDefinitions"],
    }
    store = {COMMON_URL: schema_subset["common_definitions"]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        resolver = jsonschema.RefResolver.from_schema(schema, store=store)
        return Draft4Validator(schema, resolver=resolver)


def assert_resource_valid(schema_subset: dict, resource_def_name: str, instance: dict) -> None:
    validator = make_resource_validator(schema_subset, resource_def_name)
    errors = list(validator.iter_errors(instance))
    if errors:
        formatted = "\n".join(f"  - {'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors)
        raise AssertionError(
            f"resource {instance.get('name')!r} did not validate against "
            f"resourceDefinitions/{resource_def_name}:\n{formatted}"
        )

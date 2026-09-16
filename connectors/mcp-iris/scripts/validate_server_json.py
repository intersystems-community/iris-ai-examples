#!/usr/bin/env python3
"""Validate registry/mcp-registry/server.json against the real, fetched MCP
registry JSON Schema.

The schema file this script validates against
(``registry/mcp-registry/server.schema.json``) is a byte-for-byte copy of
what was fetched, read-only, from:

    https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json

...which is the exact ``$schema`` URL used in the current
``modelcontextprotocol/registry`` documentation examples
(``docs/reference/server-json/generic-server-json.md``, fetched from
``raw.githubusercontent.com/modelcontextprotocol/registry/main/...`` in the
same session). Nothing here is hand-written from memory of what the schema
"probably" looks like.

Usage:
    python scripts/validate_server_json.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import jsonschema

HERE = pathlib.Path(__file__).resolve().parent
REGISTRY_DIR = HERE.parent / "registry" / "mcp-registry"


def main() -> int:
    schema_path = REGISTRY_DIR / "server.schema.json"
    instance_path = REGISTRY_DIR / "server.json"

    schema = json.loads(schema_path.read_text())
    instance = json.loads(instance_path.read_text())

    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)

    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        print(f"FAIL: {instance_path} does not conform to {schema_path.name}")
        for error in errors:
            location = "/".join(str(p) for p in error.path) or "<root>"
            print(f"  - at {location}: {error.message}")
        return 1

    print(f"OK: {instance_path} conforms to {schema_path.name}")
    print(f"    (schema $id: {schema.get('$id')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

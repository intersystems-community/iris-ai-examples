"""Builds the OData v4 $metadata document (CSDL/EDMX) for a Schema.

Reference: OASIS OData Version 4.0 Part 3: Common Schema Definition
Language (CSDL). This module produces the subset needed for read-only
entity sets: EntityType/Key/Property and an EntityContainer of EntitySets.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .schema import Schema

EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"
EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"


def build_metadata_xml(schema: Schema) -> str:
    """Returns the $metadata document as a UTF-8 XML string."""

    ET.register_namespace("edmx", EDMX_NS)
    ET.register_namespace("edm", EDM_NS)

    edmx = ET.Element(f"{{{EDMX_NS}}}Edmx", {"Version": "4.0"})
    data_services = ET.SubElement(edmx, f"{{{EDMX_NS}}}DataServices")
    ns_schema = ET.SubElement(
        data_services, f"{{{EDM_NS}}}Schema", {"Namespace": schema.namespace}
    )

    for entity_set in schema.entity_sets:
        entity_type = ET.SubElement(
            ns_schema, f"{{{EDM_NS}}}EntityType", {"Name": entity_set.name}
        )
        key_el = ET.SubElement(entity_type, f"{{{EDM_NS}}}Key")
        ET.SubElement(key_el, f"{{{EDM_NS}}}PropertyRef", {"Name": entity_set.key})
        for column in entity_set.columns:
            attrs = {"Name": column.name, "Type": column.edm_type}
            if column.nullable:
                attrs["Nullable"] = "true"
            else:
                attrs["Nullable"] = "false"
            ET.SubElement(entity_type, f"{{{EDM_NS}}}Property", attrs)

    container = ET.SubElement(
        ns_schema, f"{{{EDM_NS}}}EntityContainer", {"Name": "Container"}
    )
    for entity_set in schema.entity_sets:
        ET.SubElement(
            container,
            f"{{{EDM_NS}}}EntitySet",
            {
                "Name": entity_set.name,
                "EntityType": f"{schema.namespace}.{entity_set.name}",
            },
        )

    xml_bytes = ET.tostring(edmx, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")

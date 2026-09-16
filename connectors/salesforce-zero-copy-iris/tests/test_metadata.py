from __future__ import annotations

import xml.etree.ElementTree as ET

from odata_iris.metadata_xml import EDM_NS, EDMX_NS, build_metadata_xml


def test_metadata_document_is_well_formed_xml(schema):
    xml_text = build_metadata_xml(schema)
    ET.fromstring(xml_text)  # raises on malformed XML


def test_metadata_root_is_edmx(schema):
    xml_text = build_metadata_xml(schema)
    root = ET.fromstring(xml_text)
    assert root.tag == f"{{{EDMX_NS}}}Edmx"
    assert root.attrib["Version"] == "4.0"


def test_metadata_has_one_entity_type_per_entity_set(schema):
    root = ET.fromstring(build_metadata_xml(schema))
    entity_types = root.findall(f".//{{{EDM_NS}}}EntityType")
    assert [et.attrib["Name"] for et in entity_types] == ["Patient"]


def test_metadata_entity_type_declares_key(schema):
    root = ET.fromstring(build_metadata_xml(schema))
    entity_type = root.find(f".//{{{EDM_NS}}}EntityType[@Name='Patient']")
    key_refs = entity_type.findall(f"{{{EDM_NS}}}Key/{{{EDM_NS}}}PropertyRef")
    assert [k.attrib["Name"] for k in key_refs] == ["PatientID"]


def test_metadata_properties_match_schema_with_edm_types(schema):
    root = ET.fromstring(build_metadata_xml(schema))
    entity_type = root.find(f".//{{{EDM_NS}}}EntityType[@Name='Patient']")
    props = {
        p.attrib["Name"]: p.attrib["Type"]
        for p in entity_type.findall(f"{{{EDM_NS}}}Property")
    }
    assert props == {
        "PatientID": "Edm.Int64",
        "LastName": "Edm.String",
        "FirstName": "Edm.String",
        "BirthDate": "Edm.Date",
        "RiskScore": "Edm.Decimal",
    }


def test_metadata_key_property_is_not_nullable(schema):
    root = ET.fromstring(build_metadata_xml(schema))
    entity_type = root.find(f".//{{{EDM_NS}}}EntityType[@Name='Patient']")
    key_prop = entity_type.find(f"{{{EDM_NS}}}Property[@Name='PatientID']")
    assert key_prop.attrib["Nullable"] == "false"


def test_metadata_entity_container_lists_entity_sets(schema):
    root = ET.fromstring(build_metadata_xml(schema))
    container = root.find(f".//{{{EDM_NS}}}EntityContainer")
    entity_sets = container.findall(f"{{{EDM_NS}}}EntitySet")
    assert len(entity_sets) == 1
    assert entity_sets[0].attrib["Name"] == "Patient"
    assert entity_sets[0].attrib["EntityType"] == "IRISHealth.Patient"


def test_metadata_reflects_multiple_entity_sets():
    from odata_iris.schema import Column, EntitySet, Schema

    two_table_schema = Schema(
        namespace="IRISHealth",
        entity_sets=(
            EntitySet(
                name="Patient",
                table="SQLUser.Patient",
                key="PatientID",
                columns=(Column("PatientID", "BIGINT", nullable=False),),
            ),
            EntitySet(
                name="Encounter",
                table="SQLUser.Encounter",
                key="EncounterID",
                columns=(Column("EncounterID", "BIGINT", nullable=False),),
            ),
        ),
    )
    root = ET.fromstring(build_metadata_xml(two_table_schema))
    entity_types = root.findall(f".//{{{EDM_NS}}}EntityType")
    assert sorted(et.attrib["Name"] for et in entity_types) == ["Encounter", "Patient"]

import pytest

from databricks.ddl import (
    DEFAULT_EXTERNAL_OPTIONS_ALLOW_LIST,
    InvalidDdl,
    JdbcConnectionSpec,
    build_create_connection_ddl,
    build_create_foreign_catalog_ddl,
    build_drop_connection_ddl,
    validate_create_connection_grammar,
    validate_create_foreign_catalog_grammar,
)


def _spec(**overrides):
    defaults = dict(
        connection_name="iris_federation",
        host="iris.example-hospital.internal",
        port=1972,
        namespace="HSFHIR",
        user="spark_reader",
        password="s3cret",
        jar_volume_path="/Volumes/main/drivers/jars/intersystems-jdbc-3.8.jar",
    )
    defaults.update(overrides)
    return JdbcConnectionSpec(**defaults)


def test_create_connection_ddl_contains_required_clauses():
    ddl = build_create_connection_ddl(_spec())
    assert "CREATE CONNECTION IF NOT EXISTS iris_federation TYPE JDBC" in ddl
    assert "ENVIRONMENT (" in ddl
    assert "java_dependencies '[\"/Volumes/main/drivers/jars/intersystems-jdbc-3.8.jar\"]'" in ddl
    assert "url 'jdbc:IRIS://iris.example-hospital.internal:1972/HSFHIR'" in ddl
    assert "user 'spark_reader'" in ddl
    assert "password 's3cret'" in ddl
    assert f"externalOptionsAllowList '{DEFAULT_EXTERNAL_OPTIONS_ALLOW_LIST}'" in ddl


def test_create_connection_ddl_passes_grammar_validator():
    ddl = build_create_connection_ddl(_spec())
    validate_create_connection_grammar(ddl)  # must not raise


def test_create_connection_ddl_escapes_single_quote_in_password():
    ddl = build_create_connection_ddl(_spec(password="p'a'ss"))
    assert "p''a''ss" in ddl
    validate_create_connection_grammar(ddl)


def test_jar_volume_path_must_be_uc_volume():
    with pytest.raises(InvalidDdl):
        _spec(jar_volume_path="/dbfs/mnt/jars/intersystems-jdbc.jar")


def test_connection_name_must_be_safe_identifier():
    with pytest.raises(Exception):
        _spec(connection_name="bad name")


def test_forbidden_allow_list_entries_rejected():
    with pytest.raises(InvalidDdl):
        _spec(external_options_allow_list="dbtable,host")


def test_create_foreign_catalog_ddl_shape():
    ddl = build_create_foreign_catalog_ddl("iris_federation_catalog", "iris_federation", "HSFHIR")
    assert ddl == (
        "CREATE FOREIGN CATALOG IF NOT EXISTS iris_federation_catalog\n"
        "USING CONNECTION iris_federation\n"
        "OPTIONS (database 'HSFHIR');"
    )
    validate_create_foreign_catalog_grammar(ddl)


def test_drop_connection_ddl():
    assert build_drop_connection_ddl("iris_federation") == "DROP CONNECTION IF EXISTS iris_federation;"


def test_grammar_validator_rejects_missing_options_block():
    malformed = "CREATE CONNECTION iris_federation TYPE JDBC\nENVIRONMENT (\n  java_dependencies '[]'\n)\n;"
    with pytest.raises(InvalidDdl):
        validate_create_connection_grammar(malformed)


def test_grammar_validator_rejects_missing_password_option():
    malformed = (
        "CREATE CONNECTION iris_federation TYPE JDBC\n"
        "ENVIRONMENT (\n  java_dependencies '[\"x.jar\"]'\n)\n"
        "OPTIONS (\n  url 'jdbc:IRIS://h:1/N',\n  user 'u'\n);"
    )
    with pytest.raises(InvalidDdl):
        validate_create_connection_grammar(malformed)


def test_grammar_validator_rejects_unbalanced_quote():
    malformed = (
        "CREATE CONNECTION iris_federation TYPE JDBC\n"
        "ENVIRONMENT (\n  java_dependencies '[\"x.jar\"]'\n)\n"
        "OPTIONS (\n  url 'jdbc:IRIS://h:1/N,\n  user 'u',\n  password 'p'\n);"
    )
    with pytest.raises(InvalidDdl):
        validate_create_connection_grammar(malformed)


def test_grammar_validator_rejects_foreign_catalog_missing_using_connection():
    malformed = "CREATE FOREIGN CATALOG cat\nOPTIONS (database 'HSFHIR');"
    with pytest.raises(InvalidDdl):
        validate_create_foreign_catalog_grammar(malformed)

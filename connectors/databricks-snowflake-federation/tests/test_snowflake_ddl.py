import pytest

from snowflake.ddl import (
    ExternalAccessSpec,
    InvalidDdl,
    build_all_ddl,
    build_external_access_integration_ddl,
    build_network_rule_ddl,
    build_secret_ddl,
    validate_external_access_integration_grammar,
    validate_network_rule_grammar,
    validate_secret_grammar,
)


def _spec(**overrides):
    defaults = dict(
        network_rule_name="iris_pgwire_network_rule",
        secret_name="iris_pgwire_secret",
        integration_name="iris_pgwire_access_integration",
        host="iris.example-hospital.internal",
        port=5432,
        user="_SYSTEM",
        password="s3cret",
    )
    defaults.update(overrides)
    return ExternalAccessSpec(**defaults)


def test_network_rule_ddl_shape_and_grammar():
    ddl = build_network_rule_ddl(_spec())
    assert "CREATE OR REPLACE NETWORK RULE iris_pgwire_network_rule" in ddl
    assert "VALUE_LIST = ('iris.example-hospital.internal:5432');" in ddl
    validate_network_rule_grammar(ddl)


def test_secret_ddl_shape_and_grammar():
    ddl = build_secret_ddl(_spec())
    assert "CREATE OR REPLACE SECRET iris_pgwire_secret" in ddl
    assert "USERNAME = '_SYSTEM'" in ddl
    assert "PASSWORD = 's3cret'" in ddl
    validate_secret_grammar(ddl)


def test_secret_ddl_escapes_quote_in_password():
    ddl = build_secret_ddl(_spec(password="p'ss"))
    assert "p''ss" in ddl
    validate_secret_grammar(ddl)


def test_integration_ddl_references_rule_and_secret_by_name():
    ddl = build_external_access_integration_ddl(_spec())
    assert "ALLOWED_NETWORK_RULES = (iris_pgwire_network_rule)" in ddl
    assert "ALLOWED_AUTHENTICATION_SECRETS = (iris_pgwire_secret)" in ddl
    assert "ENABLED = TRUE;" in ddl
    validate_external_access_integration_grammar(ddl)


def test_build_all_ddl_returns_three_statements_in_order():
    statements = build_all_ddl(_spec())
    assert len(statements) == 3
    assert statements[0].startswith("CREATE OR REPLACE NETWORK RULE")
    assert statements[1].startswith("CREATE OR REPLACE SECRET")
    assert statements[2].startswith("CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION")


@pytest.mark.parametrize("field", ["network_rule_name", "secret_name", "integration_name"])
def test_spec_rejects_unsafe_identifiers(field):
    with pytest.raises(Exception):
        _spec(**{field: "not a valid identifier"})


def test_spec_rejects_bad_port():
    with pytest.raises(Exception):
        _spec(port=99999)


def test_grammar_validator_rejects_wrong_mode():
    malformed = (
        "CREATE OR REPLACE NETWORK RULE r\n"
        "  MODE = INGRESS\n"
        "  TYPE = HOST_PORT\n"
        "  VALUE_LIST = ('h:1');"
    )
    with pytest.raises(InvalidDdl):
        validate_network_rule_grammar(malformed)


def test_grammar_validator_rejects_integration_missing_enabled():
    malformed = (
        "CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION i\n"
        "  ALLOWED_NETWORK_RULES = (r)\n"
        "  ALLOWED_AUTHENTICATION_SECRETS = (s)\n"
        "  ENABLED = FALSE;"
    )
    with pytest.raises(InvalidDdl):
        validate_external_access_integration_grammar(malformed)

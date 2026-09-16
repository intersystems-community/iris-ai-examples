import pytest

from iris_connector.config import ConfigurationError, DEFAULT_PORT, validate_configuration

VALID = {
    "host": "iris.example.com",
    "namespace": "USER",
    "username": "demo",
    "password": "demo-pw",
}


def test_valid_minimal_configuration_uses_defaults():
    cfg = validate_configuration(dict(VALID))
    assert cfg.host == "iris.example.com"
    assert cfg.port == DEFAULT_PORT
    assert cfg.namespace == "USER"
    assert cfg.username == "demo"
    assert cfg.password == "demo-pw"
    assert cfg.schema == "SQLUser"
    assert cfg.table_allowlist is None
    assert cfg.cursor_fields is None
    assert cfg.batch_size > 0


@pytest.mark.parametrize("missing_key", ["host", "namespace", "username", "password"])
def test_missing_required_field_raises_configuration_error(missing_key):
    bad = dict(VALID)
    del bad[missing_key]
    with pytest.raises(ConfigurationError, match=missing_key):
        validate_configuration(bad)


def test_blank_required_field_raises_configuration_error():
    bad = dict(VALID)
    bad["host"] = "   "
    with pytest.raises(ConfigurationError, match="host"):
        validate_configuration(bad)


def test_none_configuration_raises_configuration_error():
    with pytest.raises(ConfigurationError):
        validate_configuration(None)


def test_non_dict_configuration_raises_configuration_error():
    with pytest.raises(ConfigurationError):
        validate_configuration(["not", "a", "dict"])


@pytest.mark.parametrize("bad_port", ["not-a-number", "3.14", ""])
def test_non_integer_port_raises_configuration_error(bad_port):
    cfg = dict(VALID)
    if bad_port == "":
        # Empty string means "use default" -- not an error. Skip.
        pytest.skip("empty string means default")
    cfg["port"] = bad_port
    with pytest.raises(ConfigurationError, match="port"):
        validate_configuration(cfg)


@pytest.mark.parametrize("bad_port", ["0", "-1", "65536", "100000"])
def test_out_of_range_port_raises_configuration_error(bad_port):
    cfg = dict(VALID)
    cfg["port"] = bad_port
    with pytest.raises(ConfigurationError, match="port"):
        validate_configuration(cfg)


def test_valid_port_string_is_coerced_to_int():
    cfg = dict(VALID)
    cfg["port"] = "51773"
    assert validate_configuration(cfg).port == 51773


def test_non_positive_batch_size_raises_configuration_error():
    cfg = dict(VALID)
    cfg["batch_size"] = "0"
    with pytest.raises(ConfigurationError, match="batch_size"):
        validate_configuration(cfg)


def test_table_allowlist_parses_csv():
    cfg = dict(VALID)
    cfg["tables"] = "PATIENT, ENCOUNTER ,LAB_RESULT"
    parsed = validate_configuration(cfg)
    assert parsed.table_allowlist == ["PATIENT", "ENCOUNTER", "LAB_RESULT"]


def test_cursor_fields_parses_json_object():
    cfg = dict(VALID)
    cfg["cursor_fields"] = '{"PATIENT": "LAST_UPDATED"}'
    parsed = validate_configuration(cfg)
    assert parsed.cursor_fields == {"PATIENT": "LAST_UPDATED"}


def test_cursor_fields_rejects_non_json():
    cfg = dict(VALID)
    cfg["cursor_fields"] = "not json"
    with pytest.raises(ConfigurationError, match="cursor_fields"):
        validate_configuration(cfg)


def test_cursor_fields_rejects_non_object_json():
    cfg = dict(VALID)
    cfg["cursor_fields"] = "[1, 2, 3]"
    with pytest.raises(ConfigurationError, match="cursor_fields"):
        validate_configuration(cfg)


def test_cursor_fields_table_must_be_in_allowlist_when_both_given():
    cfg = dict(VALID)
    cfg["tables"] = "PATIENT"
    cfg["cursor_fields"] = '{"ENCOUNTER": "VISIT_AT"}'
    with pytest.raises(ConfigurationError, match="cursor_fields"):
        validate_configuration(cfg)


def test_non_string_configuration_value_raises_configuration_error():
    cfg = dict(VALID)
    cfg["host"] = 12345
    with pytest.raises(ConfigurationError, match="host"):
        validate_configuration(cfg)

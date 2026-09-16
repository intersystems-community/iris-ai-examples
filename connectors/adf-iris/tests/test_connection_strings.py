"""Connection-string correctness across parameter permutations."""
import pytest

from generator import IrisConnectionConfig, build_connection_string, parse_connection_string


def _config(**overrides):
    defaults = dict(
        host="iris-prod.internal",
        username="adf_reader",
        key_vault_secret_name="iris-adf-reader-pwd",
    )
    defaults.update(overrides)
    return IrisConnectionConfig(**defaults)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"port": 51972},
        {"namespace": "HSFHIR"},
        {"namespace": "SQLUser"},
        {"host": "10.0.4.17"},
        {"host": "iris-prod.contoso.internal.example"},
        {"driver_name": "InterSystems ODBC"},
        {"driver_name": "InterSystems IRIS ODBC35"},
        {"extra_odbc_params": {"LogFile": "/tmp/odbc.log"}},
        {"extra_odbc_params": {"Static Cursors": "1", "Query Timeout": "0"}},
    ],
)
def test_round_trips_for_every_permutation(overrides):
    config = _config(**overrides)
    cs = build_connection_string(config)
    parsed = parse_connection_string(cs)

    assert parsed["Server"] == config.host
    assert parsed["Port"] == str(config.port)
    assert parsed["Database"] == config.namespace
    assert parsed["UID"] == config.username
    assert parsed["Driver"] == config.driver_name
    for key, value in config.extra_odbc_params.items():
        assert parsed[key] == str(value)


def test_default_port_and_namespace():
    config = _config()
    assert config.port == 1972
    assert config.namespace == "USER"
    cs = build_connection_string(config)
    assert "Port=1972" in cs
    assert "Database=USER" in cs


@pytest.mark.parametrize("bad_port", [0, -1, 65536, 100000])
def test_invalid_port_rejected(bad_port):
    with pytest.raises(ValueError):
        _config(port=bad_port)


def test_missing_host_rejected():
    with pytest.raises(ValueError):
        IrisConnectionConfig(host="", username="u", key_vault_secret_name="s")


def test_missing_username_rejected():
    with pytest.raises(ValueError):
        IrisConnectionConfig(host="h", username="", key_vault_secret_name="s")


def test_value_containing_delimiter_is_braced():
    """A value containing ';' or '=' must be wrapped in {..} per ODBC
    connection-string grammar, or it silently truncates/corrupts the rest of
    the string -- this is the class of bug behind some of the "connects and
    lists tables but fails to read rows" reports (see README)."""
    config = _config(namespace="NS;WITH=DELIM")
    cs = build_connection_string(config)
    assert "Database={NS;WITH=DELIM}" in cs
    parsed = parse_connection_string(cs)
    assert parsed["Database"] == "NS;WITH=DELIM"


def test_connection_string_never_contains_pwd_keyword():
    config = _config()
    cs = build_connection_string(config)
    assert "PWD" not in cs.upper()


def test_connection_string_is_stable_key_order_for_same_input():
    """Determinism: calling twice with identical input produces byte-identical
    output (needed so regenerating a template for CI diffing doesn't create
    spurious churn)."""
    config = _config(extra_odbc_params={"LogFile": "/tmp/a.log", "Query Timeout": "5"})
    assert build_connection_string(config) == build_connection_string(config)

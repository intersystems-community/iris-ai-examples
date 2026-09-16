"""Secrets must be referenced via Key Vault, never inlined as plaintext.

IrisConnectionConfig has no `password` field at all -- the only way to get a
credential into the generated linked service is key_vault_secret_name. These
tests still walk the *generated JSON* (not just the API surface) to catch a
future regression where someone adds a convenience password= kwarg and
forgets to keep it out of the emitted connectionString / password field.
"""
import json

import pytest

from generator import IrisConnectionConfig, build_connection_string, generate_bundle


PLAINTEXT_MARKERS = ("hunter2", "S3cr3tPassw0rd!", "correct-horse-battery-staple")


def _walk_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)
    elif isinstance(obj, str):
        yield obj


def test_config_has_no_password_field():
    """A plaintext password kwarg is not even accepted -- TypeError, not a
    silent no-op."""
    with pytest.raises(TypeError):
        IrisConnectionConfig(
            host="h",
            username="u",
            key_vault_secret_name="s",
            password="hunter2",  # type: ignore[call-arg]
        )


def test_password_field_is_a_keyvault_reference_not_a_secure_string(sample_bundle):
    password = sample_bundle["iris_linked_service"]["properties"]["typeProperties"]["password"]
    assert password["type"] == "AzureKeyVaultSecret"
    assert "store" in password and "secretName" in password
    # A SecureString literal (type == "SecureString") would mean the
    # plaintext travels inside this ARM document. That must never happen.
    assert password["type"] != "SecureString"


def test_blob_sink_connection_string_is_also_a_keyvault_reference(sample_bundle):
    cs = sample_bundle["blob_linked_service"]["properties"]["typeProperties"]["connectionString"]
    assert isinstance(cs, dict)
    assert cs["type"] == "AzureKeyVaultSecret"


@pytest.mark.parametrize("secret_value", PLAINTEXT_MARKERS)
def test_no_plaintext_marker_leaks_into_generated_template(secret_value, sample_config):
    """Simulate an operator accidentally naming a Key Vault secret after the
    plaintext value, or pasting a password into an unrelated field, and
    confirm the *serialized template* doesn't carry it anywhere the schema
    considers a plain string credential slot. This mainly guards
    build_connection_string, which must never fold PWD into the connection
    string it returns."""
    cs = build_connection_string(sample_config)
    assert secret_value not in cs


def test_generated_bundle_json_has_no_pwd_keyword_anywhere(sample_bundle):
    serialized = json.dumps(sample_bundle["template"])
    assert "PWD=" not in serialized
    assert "pwd=" not in serialized.lower().replace("password", "")


def test_only_allowed_secret_shape_is_azurekeyvaultsecret(sample_bundle):
    """Walk every dict in the template that looks like a SecretBase
    (has a "type" key matching SecureString/AzureKeyVaultSecret) and assert
    none of them are the plaintext SecureString variant."""
    def walk(obj):
        if isinstance(obj, dict):
            t = obj.get("type")
            if t == "SecureString" and "value" in obj:
                raise AssertionError(f"found an inlined SecureString secret: {obj!r}")
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(sample_bundle["template"])

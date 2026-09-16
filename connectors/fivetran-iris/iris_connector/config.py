"""Configuration parsing and validation.

Fivetran hands connector code a `configuration: dict` in which *every value
is a string* -- whether it was typed into the connection's Setup form in the
Fivetran dashboard or written into a local `configuration.json` for
`fivetran debug`. See:
https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json

This module is the single place that turns those strings into a typed,
validated `IRISConfig`, and raises `ConfigurationError` with a specific,
actionable message the moment something required is missing or malformed.
Nothing else in this package should read `configuration` directly.
"""

from dataclasses import dataclass
from typing import List, Optional

DEFAULT_PORT = 1972
DEFAULT_SCHEMA = "SQLUser"
DEFAULT_BATCH_SIZE = 5000
DEFAULT_CONNECTION_TIMEOUT = 10

_REQUIRED_FIELDS = ("host", "namespace", "username", "password")


class ConfigurationError(ValueError):
    """Raised when the supplied connector configuration is missing or invalid.

    `Connector.debug`/`deploy` surface this as a normal Python exception with
    a traceback; `schema()`/`update()` should let it propagate rather than
    catching it, so the setup/sync failure message in the Fivetran dashboard
    is this message, not a generic connection error three layers down.
    """


@dataclass(frozen=True)
class IRISConfig:
    """Validated, typed connection + sync configuration."""

    host: str
    port: int
    namespace: str
    username: str
    password: str
    schema: str = DEFAULT_SCHEMA
    table_allowlist: Optional[List[str]] = None
    cursor_fields: Optional[dict] = None
    batch_size: int = DEFAULT_BATCH_SIZE
    connection_timeout: int = DEFAULT_CONNECTION_TIMEOUT


def _require_str(configuration: dict, key: str) -> str:
    value = configuration.get(key)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ConfigurationError(
            f"configuration.{key} is required. Set it in configuration.json "
            f"(local `fivetran debug`) or in the connection's Setup form in "
            f"the Fivetran dashboard."
        )
    if not isinstance(value, str):
        raise ConfigurationError(
            f"configuration.{key} must be a string, got {type(value).__name__}: {value!r}. "
            f"Fivetran configuration values are always strings; something upstream "
            f"passed a non-string value."
        )
    return value


def _parse_int(configuration: dict, key: str, default: int) -> int:
    raw = configuration.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise ConfigurationError(
            f"configuration.{key} must be an integer, got {raw!r}."
        )


def _parse_csv_list(configuration: dict, key: str) -> Optional[List[str]]:
    raw = configuration.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    items = [item.strip() for item in str(raw).split(",") if item.strip()]
    return items or None


def _parse_cursor_fields(configuration: dict, key: str = "cursor_fields") -> Optional[dict]:
    """Parses the optional `cursor_fields` config value.

    Expected format is a JSON object mapping table name -> cursor column name,
    e.g. '{"PATIENT": "UPDATED_AT", "LAB_RESULT": "ID"}'. Tables *not* listed
    here are synced full-refresh (truncate + reload) instead of incrementally.
    """
    raw = configuration.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    import json

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"configuration.{key} must be a JSON object string mapping table "
            f'name to cursor column, e.g. \'{{"PATIENT": "UPDATED_AT"}}\'. '
            f"Got {raw!r} ({exc})."
        )
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        raise ConfigurationError(
            f"configuration.{key} must decode to a JSON object of string table "
            f"names to string column names. Got: {parsed!r}."
        )
    return parsed


def validate_configuration(configuration: Optional[dict]) -> IRISConfig:
    """Validates `configuration` and returns a typed `IRISConfig`.

    Raises:
        ConfigurationError: with a specific, user-facing message identifying
            exactly which field is missing or malformed.
    """
    if configuration is None:
        raise ConfigurationError(
            "configuration must not be None. Pass at least an empty dict; "
            "required fields will be reported individually."
        )
    if not isinstance(configuration, dict):
        raise ConfigurationError(
            f"configuration must be a dict, got {type(configuration).__name__}."
        )

    missing = [key for key in _REQUIRED_FIELDS if not str(configuration.get(key, "")).strip()]
    if missing:
        raise ConfigurationError(
            "configuration is missing required field(s): "
            + ", ".join(missing)
            + ". Required fields are: " + ", ".join(_REQUIRED_FIELDS) + "."
        )

    host = _require_str(configuration, "host")
    namespace = _require_str(configuration, "namespace")
    username = _require_str(configuration, "username")
    password = _require_str(configuration, "password")

    port = _parse_int(configuration, "port", DEFAULT_PORT)
    if not (1 <= port <= 65535):
        raise ConfigurationError(f"configuration.port must be between 1 and 65535, got {port}.")

    batch_size = _parse_int(configuration, "batch_size", DEFAULT_BATCH_SIZE)
    if batch_size <= 0:
        raise ConfigurationError(
            f"configuration.batch_size must be a positive integer, got {batch_size}."
        )

    connection_timeout = _parse_int(
        configuration, "connection_timeout", DEFAULT_CONNECTION_TIMEOUT
    )
    if connection_timeout <= 0:
        raise ConfigurationError(
            f"configuration.connection_timeout must be a positive integer, "
            f"got {connection_timeout}."
        )

    schema = configuration.get("schema") or DEFAULT_SCHEMA
    if not isinstance(schema, str) or not schema.strip():
        raise ConfigurationError(
            f"configuration.schema must be a non-empty string, got {schema!r}."
        )

    table_allowlist = _parse_csv_list(configuration, "tables")
    cursor_fields = _parse_cursor_fields(configuration, "cursor_fields")

    if cursor_fields and table_allowlist:
        unknown = sorted(set(cursor_fields) - set(table_allowlist))
        if unknown:
            raise ConfigurationError(
                "configuration.cursor_fields names table(s) not present in "
                f"configuration.tables: {', '.join(unknown)}."
            )

    return IRISConfig(
        host=host,
        port=port,
        namespace=namespace,
        username=username,
        password=password,
        schema=schema,
        table_allowlist=table_allowlist,
        cursor_fields=cursor_fields,
        batch_size=batch_size,
        connection_timeout=connection_timeout,
    )

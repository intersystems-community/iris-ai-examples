"""Build the DDL for the recommended Snowflake-side path: an External
Access Integration that lets a Snowpark Python function reach IRIS (either
via iris-pgwire over the plain DB-API/psycopg2 path, which is GA, or via
the native IRIS JDBC driver through Snowpark's JDBC API, which is public
preview as of this research). See ../README.md ("Path B: Snowflake") for
the doc citations backing this shape.

Three objects, created in this order (each references the previous by
name, so order matters for a human running these by hand -- this module
does not execute them, it only renders the text):

    CREATE OR REPLACE NETWORK RULE <rule_name>
      MODE = EGRESS
      TYPE = HOST_PORT
      VALUE_LIST = ('<host>:<port>');

    CREATE OR REPLACE SECRET <secret_name>
      TYPE = PASSWORD
      USERNAME = '<user>'
      PASSWORD = '<password>';

    CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION <integration_name>
      ALLOWED_NETWORK_RULES = (<rule_name>)
      ALLOWED_AUTHENTICATION_SECRETS = (<secret_name>)
      ENABLED = TRUE;
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.iris_jdbc import escape_sql_literal, validate_host, validate_identifier, validate_port


class InvalidDdl(ValueError):
    pass


@dataclass(frozen=True)
class ExternalAccessSpec:
    network_rule_name: str
    secret_name: str
    integration_name: str
    host: str
    port: int
    user: str
    password: str

    def __post_init__(self) -> None:
        validate_identifier(self.network_rule_name, what="network_rule_name")
        validate_identifier(self.secret_name, what="secret_name")
        validate_identifier(self.integration_name, what="integration_name")
        validate_host(self.host)
        validate_port(self.port)
        if not self.user:
            raise InvalidDdl("user must be non-empty")


def build_network_rule_ddl(spec: ExternalAccessSpec) -> str:
    return (
        f"CREATE OR REPLACE NETWORK RULE {spec.network_rule_name}\n"
        f"  MODE = EGRESS\n"
        f"  TYPE = HOST_PORT\n"
        f"  VALUE_LIST = ('{escape_sql_literal(spec.host)}:{spec.port}');"
    )


def build_secret_ddl(spec: ExternalAccessSpec) -> str:
    return (
        f"CREATE OR REPLACE SECRET {spec.secret_name}\n"
        f"  TYPE = PASSWORD\n"
        f"  USERNAME = '{escape_sql_literal(spec.user)}'\n"
        f"  PASSWORD = '{escape_sql_literal(spec.password)}';"
    )


def build_external_access_integration_ddl(spec: ExternalAccessSpec) -> str:
    return (
        f"CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION {spec.integration_name}\n"
        f"  ALLOWED_NETWORK_RULES = ({spec.network_rule_name})\n"
        f"  ALLOWED_AUTHENTICATION_SECRETS = ({spec.secret_name})\n"
        f"  ENABLED = TRUE;"
    )


def build_all_ddl(spec: ExternalAccessSpec) -> list[str]:
    """Return the three statements in the order they must be run."""
    return [
        build_network_rule_ddl(spec),
        build_secret_ddl(spec),
        build_external_access_integration_ddl(spec),
    ]


# --- Offline grammar validation --------------------------------------------

_NETWORK_RULE_RE = re.compile(
    r"^CREATE OR REPLACE NETWORK RULE [A-Za-z_][A-Za-z0-9_]*\n"
    r"  MODE = EGRESS\n"
    r"  TYPE = HOST_PORT\n"
    r"  VALUE_LIST = \('.+:\d+'\);$",
    re.DOTALL,
)

_SECRET_RE = re.compile(
    r"^CREATE OR REPLACE SECRET [A-Za-z_][A-Za-z0-9_]*\n"
    r"  TYPE = PASSWORD\n"
    r"  USERNAME = '.*'\n"
    r"  PASSWORD = '.*';$",
    re.DOTALL,
)

_INTEGRATION_RE = re.compile(
    r"^CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION [A-Za-z_][A-Za-z0-9_]*\n"
    r"  ALLOWED_NETWORK_RULES = \([A-Za-z_][A-Za-z0-9_]*\)\n"
    r"  ALLOWED_AUTHENTICATION_SECRETS = \([A-Za-z_][A-Za-z0-9_]*\)\n"
    r"  ENABLED = TRUE;$",
    re.DOTALL,
)


def validate_network_rule_grammar(ddl: str) -> None:
    if not _NETWORK_RULE_RE.match(ddl):
        raise InvalidDdl("DDL does not match documented CREATE NETWORK RULE grammar")


def validate_secret_grammar(ddl: str) -> None:
    if not _SECRET_RE.match(ddl):
        raise InvalidDdl("DDL does not match documented CREATE SECRET grammar")


def validate_external_access_integration_grammar(ddl: str) -> None:
    if not _INTEGRATION_RE.match(ddl):
        raise InvalidDdl(
            "DDL does not match documented CREATE EXTERNAL ACCESS INTEGRATION grammar"
        )

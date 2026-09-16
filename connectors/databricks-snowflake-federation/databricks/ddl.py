"""Build the Unity Catalog JDBC ("bring your own driver") DDL for a
Lakehouse Federation connection to InterSystems IRIS, and validate it
against the documented grammar as far as that is possible offline.

Grammar and defaults are sourced from Databricks' own JDBC connection and
CREATE CONNECTION / CREATE FOREIGN CATALOG documentation. See
../README.md ("Path A: Databricks") for the exact doc URLs and the search
evidence backing each field, since this session's network policy blocked
a direct fetch of docs.databricks.com (see ../STATUS.md).

Documented shape (JDBC Unity Catalog connection, bring-your-own-driver):

    CREATE CONNECTION <connection_name> TYPE JDBC
    ENVIRONMENT (
      java_dependencies '["<jar_volume_path>"]'
    )
    OPTIONS (
      url '<jdbc_url>',
      user '<user>',
      password '<password>',
      externalOptionsAllowList '<comma_separated_allowlist>'
    );

    CREATE FOREIGN CATALOG <catalog_name>
    USING CONNECTION <connection_name>
    OPTIONS (database '<namespace>');

The default ``externalOptionsAllowList`` documented by Databricks is
``dbtable,query,partitionColumn,lowerBound,upperBound,numPartitions`` --
this module uses that same default unless the caller overrides it.
``host``/``port``/``url`` can never be placed in the allow list; Databricks
documents that these can never be set at query time regardless of the
allow list, so this module rejects an attempt to include them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.iris_jdbc import build_jdbc_url, escape_sql_literal, validate_identifier

# Matches Databricks' own documented default. Callers may pass a different
# allow list, but this constant is what ships if they don't.
DEFAULT_EXTERNAL_OPTIONS_ALLOW_LIST = (
    "dbtable,query,partitionColumn,lowerBound,upperBound,numPartitions"
)

# Options Databricks documents as never settable at query time, regardless
# of externalOptionsAllowList, because allowing them would let a querying
# user redirect the connection to a different host.
_FORBIDDEN_ALLOW_LIST_OPTIONS = {"host", "port", "servername", "portnumber", "instancename", "url"}


class InvalidDdl(ValueError):
    pass


@dataclass(frozen=True)
class JdbcConnectionSpec:
    connection_name: str
    host: str
    port: int
    namespace: str
    user: str
    password: str
    jar_volume_path: str
    external_options_allow_list: str = DEFAULT_EXTERNAL_OPTIONS_ALLOW_LIST

    def __post_init__(self) -> None:
        validate_identifier(self.connection_name, what="connection_name")
        build_jdbc_url(self.host, self.port, self.namespace)  # validates host/port/namespace
        if not self.user:
            raise InvalidDdl("user must be non-empty")
        if not self.jar_volume_path.startswith("/Volumes/"):
            raise InvalidDdl(
                "jar_volume_path must be a Unity Catalog volume path "
                f"(/Volumes/<catalog>/<schema>/<volume>/...), got {self.jar_volume_path!r}. "
                "Databricks documents java_dependencies as volume-location-only."
            )
        requested = {tok.strip().lower() for tok in self.external_options_allow_list.split(",") if tok.strip()}
        forbidden_hit = requested & _FORBIDDEN_ALLOW_LIST_OPTIONS
        if forbidden_hit:
            raise InvalidDdl(
                f"externalOptionsAllowList must not include {sorted(forbidden_hit)}; "
                "Databricks documents these as never settable at query time"
            )


def build_create_connection_ddl(spec: JdbcConnectionSpec) -> str:
    """Render the ``CREATE CONNECTION ... TYPE JDBC`` statement for ``spec``."""
    url = build_jdbc_url(spec.host, spec.port, spec.namespace)
    return (
        f"CREATE CONNECTION IF NOT EXISTS {spec.connection_name} TYPE JDBC\n"
        f"ENVIRONMENT (\n"
        f"  java_dependencies '[\"{spec.jar_volume_path}\"]'\n"
        f")\n"
        f"OPTIONS (\n"
        f"  url '{escape_sql_literal(url)}',\n"
        f"  user '{escape_sql_literal(spec.user)}',\n"
        f"  password '{escape_sql_literal(spec.password)}',\n"
        f"  externalOptionsAllowList '{escape_sql_literal(spec.external_options_allow_list)}'\n"
        f");"
    )


def build_create_foreign_catalog_ddl(catalog_name: str, connection_name: str, namespace: str) -> str:
    """Render ``CREATE FOREIGN CATALOG ... USING CONNECTION ...``."""
    validate_identifier(catalog_name, what="catalog_name")
    validate_identifier(connection_name, what="connection_name")
    validate_identifier(namespace, what="namespace")
    return (
        f"CREATE FOREIGN CATALOG IF NOT EXISTS {catalog_name}\n"
        f"USING CONNECTION {connection_name}\n"
        f"OPTIONS (database '{escape_sql_literal(namespace)}');"
    )


def build_drop_connection_ddl(connection_name: str) -> str:
    validate_identifier(connection_name, what="connection_name")
    return f"DROP CONNECTION IF EXISTS {connection_name};"


# --- Offline grammar validation -------------------------------------------
#
# We cannot run these statements against a real Databricks SQL endpoint in
# this environment (see ../STATUS.md). What we *can* do is check that
# generated DDL matches the documented statement shape: right keywords, in
# the right order, with the clauses the docs say are required. This is a
# structural check, not a real SQL parser -- it catches builder bugs
# (missing clause, wrong keyword order, unbalanced parens/quotes), which is
# exactly the class of bug a unit test should catch here.

_CREATE_CONNECTION_RE = re.compile(
    r"^CREATE CONNECTION(?: IF NOT EXISTS)? [A-Za-z_][A-Za-z0-9_]* TYPE JDBC\n"
    r"ENVIRONMENT \(\n"
    r"  java_dependencies '\[.*\]'\n"
    r"\)\n"
    r"OPTIONS \(\n"
    r"(?:  \w+ '.*',?\n)+"
    r"\);$",
    re.DOTALL,
)

_CREATE_FOREIGN_CATALOG_RE = re.compile(
    r"^CREATE FOREIGN CATALOG(?: IF NOT EXISTS)? [A-Za-z_][A-Za-z0-9_]*\n"
    r"USING CONNECTION [A-Za-z_][A-Za-z0-9_]*\n"
    r"OPTIONS \((?:database|catalog) '.*'\);$",
    re.DOTALL,
)

_REQUIRED_CREATE_CONNECTION_OPTIONS = ("url", "user", "password")


def validate_create_connection_grammar(ddl: str) -> None:
    """Raise ``InvalidDdl`` if ``ddl`` does not match the documented
    ``CREATE CONNECTION ... TYPE JDBC`` shape (keyword order, required
    clauses, balanced quoting of the OPTIONS block).
    """
    if not _CREATE_CONNECTION_RE.match(ddl):
        raise InvalidDdl("DDL does not match documented CREATE CONNECTION ... TYPE JDBC grammar")
    for opt in _REQUIRED_CREATE_CONNECTION_OPTIONS:
        if not re.search(rf"\n  {opt} '", ddl):
            raise InvalidDdl(f"DDL is missing required OPTIONS key '{opt}'")
    if ddl.count("'") % 2 != 0:
        raise InvalidDdl("DDL has an unbalanced single quote")


def validate_create_foreign_catalog_grammar(ddl: str) -> None:
    if not _CREATE_FOREIGN_CATALOG_RE.match(ddl):
        raise InvalidDdl(
            "DDL does not match documented CREATE FOREIGN CATALOG ... USING CONNECTION grammar"
        )
    if ddl.count("'") % 2 != 0:
        raise InvalidDdl("DDL has an unbalanced single quote")

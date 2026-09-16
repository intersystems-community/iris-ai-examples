"""IRIS connectivity primitives shared by the Databricks and Snowflake
federation recipes.

Facts (see ../README.md for citations and ../STATUS.md for what has and has
not been verified in this environment):

- JDBC driver class:   com.intersystems.jdbc.IRISDriver
- JDBC URL form:       jdbc:IRIS://<host>:<port>/<namespace>
- Default superserver port: 1972
- PostgreSQL wire protocol: intersystems-community/iris-pgwire, default
  listener port 5432, DSN form postgresql://<user>:<password>@<host>:<port>/<namespace>

These two match the reference table already checked into
../../README.md (connectors/README.md) in this repo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

IRIS_JDBC_DRIVER_CLASS = "com.intersystems.jdbc.IRISDriver"
IRIS_DEFAULT_SUPERSERVER_PORT = 1972
IRIS_PGWIRE_DEFAULT_PORT = 5432

# Conservative identifier grammar shared by Databricks unquoted SQL
# identifiers, Snowflake unquoted identifiers, and IRIS namespace names:
# letter or underscore first, then letters/digits/underscore. Anything else
# must be handled by the caller (e.g. quoting), which this module refuses to
# guess at, since quoting rules differ between the two target systems.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Hostnames we accept: DNS labels, dots, and IPv4-ish content. Deliberately
# excludes whitespace, quotes, semicolons -- anything that could break out
# of a SQL string literal or a shell/DSN token.
_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\.\-]*$")


class InvalidIrisTarget(ValueError):
    """Raised when a host/port/namespace/identifier fails validation."""


def validate_identifier(name: str, *, what: str = "identifier") -> str:
    """Validate a SQL identifier (connection/catalog/integration name, etc).

    Returns ``name`` unchanged on success. Raises ``InvalidIrisTarget`` on
    anything that is not a plain, unquoted-safe identifier, so callers never
    silently emit DDL that would need quoting rules this module does not
    implement.
    """
    if not name or not _SAFE_IDENTIFIER_RE.match(name):
        raise InvalidIrisTarget(
            f"{what} {name!r} is not a safe unquoted SQL identifier "
            "(must match [A-Za-z_][A-Za-z0-9_]*)"
        )
    return name


def validate_host(host: str) -> str:
    if not host or not _SAFE_HOST_RE.match(host):
        raise InvalidIrisTarget(f"host {host!r} is not a safe hostname/IP")
    return host


def validate_port(port: int) -> int:
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port <= 65535):
        raise InvalidIrisTarget(f"port {port!r} is not a valid TCP port (1-65535)")
    return port


def escape_sql_literal(value: str) -> str:
    """Escape a value for use inside a single-quoted SQL string literal.

    Standard SQL (and both Databricks SQL and Snowflake SQL) doubles an
    embedded single quote: ``O'Brien`` -> ``O''Brien``. This is the only
    escaping this module performs -- it does not attempt to defend against
    every SQL-injection vector, because these strings are meant to be
    emitted into DDL a human reviews before running, not accepted from an
    untrusted caller at runtime.
    """
    return value.replace("'", "''")


@dataclass(frozen=True)
class IrisTarget:
    """A validated IRIS connection target, reused by every DDL builder."""

    host: str
    port: int
    namespace: str
    user: str

    def __post_init__(self) -> None:
        validate_host(self.host)
        validate_port(self.port)
        validate_identifier(self.namespace, what="namespace")
        if not self.user:
            raise InvalidIrisTarget("user must be non-empty")


def build_jdbc_url(host: str, port: int, namespace: str) -> str:
    """Build ``jdbc:IRIS://host:port/NAMESPACE``.

    Raises ``InvalidIrisTarget`` if any component would produce a malformed
    or unsafe URL.
    """
    validate_host(host)
    validate_port(port)
    validate_identifier(namespace, what="namespace")
    return f"jdbc:IRIS://{host}:{port}/{namespace}"


def build_pgwire_dsn(host: str, port: int, namespace: str, user: str, password: str) -> str:
    """Build a libpq-style DSN for connecting to IRIS through iris-pgwire.

    ``psycopg2.connect(dsn)`` and ``psycopg.connect(dsn)`` both accept this
    form directly.
    """
    validate_host(host)
    validate_port(port)
    validate_identifier(namespace, what="namespace")
    if not user:
        raise InvalidIrisTarget("user must be non-empty")
    return f"host={host} port={port} dbname={namespace} user={user} password={password}"


def build_pgwire_url(host: str, port: int, namespace: str, user: str, password: str) -> str:
    """Build a ``postgresql://`` URL form of the same DSN, for tools (e.g.
    SQLAlchemy) that want a connection URL rather than a keyword DSN.
    """
    validate_host(host)
    validate_port(port)
    validate_identifier(namespace, what="namespace")
    if not user:
        raise InvalidIrisTarget("user must be non-empty")
    return f"postgresql://{user}:{password}@{host}:{port}/{namespace}"

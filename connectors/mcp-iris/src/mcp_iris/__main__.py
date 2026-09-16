"""stdio entrypoint: ``python -m mcp_iris``.

Reads connection settings from the environment (matching the variable
names used by the Claude Desktop Extension manifest and the MCP registry
``server.json`` in ``registry/`` -- keep those three in sync if you rename
one here) and runs the MCP server over stdio.
"""

from __future__ import annotations

import os
import sys

from .db import (
    DEFAULT_ROW_CAP,
    DEFAULT_TIMEOUT_SECONDS,
    IRISConnectionConfig,
    IRISConnectionFactory,
    QueryExecutor,
)
from .server import build_server


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def main() -> None:
    hostname = os.environ.get("IRIS_HOSTNAME")
    if not hostname:
        print(
            "mcp_iris: IRIS_HOSTNAME environment variable is required "
            "(see README.md for the full list of IRIS_* variables)",
            file=sys.stderr,
        )
        raise SystemExit(2)

    config = IRISConnectionConfig(
        hostname=hostname,
        port=_env_int("IRIS_PORT", 1972),
        namespace=os.environ.get("IRIS_NAMESPACE", "USER"),
        username=os.environ.get("IRIS_USERNAME", "_SYSTEM"),
        password=os.environ.get("IRIS_PASSWORD", ""),
    )
    executor = QueryExecutor(
        IRISConnectionFactory(config),
        row_cap=_env_int("MCP_IRIS_ROW_CAP", DEFAULT_ROW_CAP),
        timeout_seconds=_env_float(
            "MCP_IRIS_QUERY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
        ),
    )
    server = build_server(executor)
    server.run("stdio")


if __name__ == "__main__":
    main()

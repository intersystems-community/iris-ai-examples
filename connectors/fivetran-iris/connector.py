"""Fivetran Connector SDK entrypoint for the IRIS source connector.

Run locally with the real `fivetran_connector_sdk` CLI (installed via
`pip install fivetran-connector-sdk`, see requirements.txt):

    fivetran debug --configuration configuration.json

`configuration.json` in this directory sets `"driver": "fake"`, which
routes `schema()`/`update()` at a fake, in-memory IRIS stand-in
(`iris_connector.fake_db.demo_connection`) instead of a real IRIS instance --
see README.md and STATUS.md for exactly why (no live IRIS in this
environment) and what that does and does not verify. Delete the `driver`
key (or set it to anything else) to connect to a real IRIS instance via
`intersystems-irispython`; see README.md for the real fields
(host/port/namespace/username/password/schema/tables/cursor_fields/batch_size).

All actual logic lives in `iris_connector/`, behind the `db.DBConnection`
interface, so it is unit-testable with `pytest` independent of this file,
the SDK runtime, and any real IRIS instance -- see `tests/`.
"""

from fivetran_connector_sdk import Connector, Logging as log, Operations as op

from iris_connector import db
from iris_connector.catalog import build_fivetran_schema, discover_schema
from iris_connector.config import validate_configuration
from iris_connector.sync import run_sync


def _connect(configuration: dict, cfg):
    """Chooses the fake, in-memory connection for the local debug demo, or a
    real IRIS connection otherwise. See the module docstring and
    STATUS.md -- `driver: fake` exists solely so `fivetran debug` can be run
    end-to-end without a live IRIS instance; it is never selected in a real
    deployment because real `configuration.json`/Setup-form values never set
    `driver` to `"fake"`.
    """
    if configuration.get("driver") == "fake":
        from iris_connector.fake_db import demo_connection

        log.info("driver=fake: using the bundled in-memory demo dataset, NOT a real IRIS instance.")
        return demo_connection()
    return db.connect(cfg)


def schema(configuration: dict):
    cfg = validate_configuration(configuration)
    connection = _connect(configuration, cfg)
    try:
        tables = discover_schema(
            connection, cfg.schema, table_allowlist=cfg.table_allowlist, warn=log.warning
        )
        return build_fivetran_schema(tables)
    finally:
        connection.close()


def update(configuration: dict, state: dict):
    cfg = validate_configuration(configuration)
    connection = _connect(configuration, cfg)
    try:
        run_sync(connection, cfg, state, ops=op, warn=log.warning)
    finally:
        connection.close()


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()

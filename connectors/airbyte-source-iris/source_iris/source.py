#
# source-iris: AbstractSource implementation.
#

from __future__ import annotations

import logging
from typing import Any, Callable, List, Mapping, Optional, Tuple

from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream

from .db import DBAPIConnection, connect_real_iris
from .iris_client import IrisClient, TableMeta
from .streams import IrisTableStream

# Type alias for the injectable "how do I get a DB-API connection from this config"
# hook. Production code never sets this explicitly (it defaults to connect_real_iris);
# tests always pass a factory that returns a FakeIrisConnection. This is the seam that
# lets `check`/`discover`/`read` all be driven end-to-end, through the real CDK
# entrypoint, without ever touching a live IRIS instance or Docker.
ConnectionFactory = Callable[[Mapping[str, Any]], DBAPIConnection]


class IrisSource(AbstractSource):
    def __init__(self, connection_factory: Optional[ConnectionFactory] = None):
        self._connection_factory: ConnectionFactory = connection_factory or connect_real_iris

    # -- connectivity --------------------------------------------------------------

    def check_connection(self, logger: logging.Logger, config: Mapping[str, Any]) -> Tuple[bool, Optional[Any]]:
        try:
            connection = self._connection_factory(config)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via AirbyteConnectionStatus
            return False, str(exc)

        try:
            IrisClient(connection).test_connection()
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            connection.close()

        return True, None

    # -- streams --------------------------------------------------------------

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        # One connection/client shared by every stream built from this call. The CDK
        # gives sources no explicit teardown hook (discover() and read() each call
        # streams() once and then use the results for the rest of that process's
        # life), so a single connection per sync/discover attempt is both simpler and
        # cheaper than one per table.
        connection = self._connection_factory(config)
        client = IrisClient(connection)

        schemas = config.get("schemas") or None
        tables = client.list_tables(schemas=schemas)

        allowed_tables = config.get("tables")
        streams: List[Stream] = []
        for table in tables:
            if allowed_tables and table.name not in allowed_tables and table.qualified_name not in allowed_tables:
                continue
            cursor_field = self._select_cursor_field(table)
            streams.append(IrisTableStream(client=client, table=table, cursor_field=cursor_field))
        return streams

    @staticmethod
    def _select_cursor_field(table: TableMeta) -> Optional[str]:
        pk = table.primary_key
        if len(pk) != 1:
            return None
        pk_column = next((c for c in table.columns if c.name == pk[0]), None)
        if pk_column is None or pk_column.is_lob:
            return None
        return pk_column.name

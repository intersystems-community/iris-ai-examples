#
# source-iris: Airbyte CDK Stream implementations.
#
# Built against airbyte-cdk==7.28.4's actual installed API (introspected directly with
# `inspect.getsource`, not guessed — the CDK's Stream/Cursor interfaces have churned
# across major versions). Incremental state uses the CDK's current recommended pattern,
# `airbyte_cdk.sources.streams.CheckpointMixin` (a `state` property getter/setter);
# the older `IncrementalMixin` is deprecated as of CDK 0.87.0 and `get_updated_state()`
# is the even-older pre-0.1.49 mechanism — see the CDK's own docstrings, reproduced in
# STATUS.md.

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Union

from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams import CheckpointMixin, Stream

from .iris_client import IrisClient, TableMeta
from .type_mapping import map_iris_type


class IrisTableStream(Stream, CheckpointMixin):
    """
    One Airbyte stream per IRIS table. Supports full refresh always, and incremental
    sync when constructed with a `cursor_field`.

    `cursor_field` must name a column whose IRIS DATA_TYPE is orderable and not a
    stream/LOB type (enforced by IrisSource before this class is even constructed —
    see source.py::IrisSource._build_stream) since IRIS rejects streams/LOBs in
    ORDER BY / WHERE (SQLCODE -313/-37).
    """

    primary_key_delimiter = "."

    def __init__(
        self,
        client: IrisClient,
        table: TableMeta,
        cursor_field: Optional[str] = None,
    ):
        self._client = client
        self._table = table
        self._configured_cursor_field = cursor_field
        self._state: Dict[str, Any] = {}

    # -- identity --------------------------------------------------------------

    @property
    def name(self) -> str:
        # Airbyte stream names must be unique per source; schema-qualify to guarantee
        # that even if two IRIS schemas both have a table with the same name.
        return f"{self._table.schema}_{self._table.name}"

    @property
    def namespace(self) -> Optional[str]:
        return self._table.schema

    # -- schema / keys --------------------------------------------------------------

    def get_json_schema(self) -> Mapping[str, Any]:
        properties: Dict[str, Any] = {}
        for column in self._table.columns:
            properties[column.name] = map_iris_type(
                column.data_type,
                is_nullable=column.is_nullable,
                numeric_precision=column.numeric_precision,
                numeric_scale=column.numeric_scale,
            )
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
        }

    @property
    def primary_key(self) -> Optional[Union[str, List[str], List[List[str]]]]:
        pk = self._table.primary_key
        if not pk:
            return None
        if len(pk) == 1:
            return pk[0]
        return [[col] for col in pk]

    @property
    def cursor_field(self) -> Union[str, List[str]]:
        return self._configured_cursor_field or []

    # -- CheckpointMixin --------------------------------------------------------------

    @property
    def state(self) -> MutableMapping[str, Any]:
        return self._state

    @state.setter
    def state(self, value: MutableMapping[str, Any]) -> None:
        self._state = dict(value or {})

    # -- reading --------------------------------------------------------------

    def _column_names(self) -> List[str]:
        return [c.name for c in self._table.columns]

    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: Optional[List[str]] = None,
        stream_slice: Optional[Mapping[str, Any]] = None,
        stream_state: Optional[Mapping[str, Any]] = None,
    ) -> Iterable[Dict[str, Any]]:
        column_names = self._column_names()

        if sync_mode == SyncMode.full_refresh or not self._configured_cursor_field:
            yield from self._client.read_full_refresh(self._table.schema, self._table.name, column_names)
            return

        cursor = self._configured_cursor_field
        start_value = (stream_state or {}).get(cursor)
        last_seen = start_value

        for record in self._client.read_incremental(
            self._table.schema,
            self._table.name,
            column_names,
            cursor,
            start_value,
        ):
            last_seen = record.get(cursor, last_seen)
            yield record
            # Checkpoint after every record so a killed sync resumes past what was
            # already emitted, per CheckpointMixin's contract.
            self.state = {cursor: last_seen}

        if last_seen is not None:
            self.state = {cursor: last_seen}

    @property
    def state_checkpoint_interval(self) -> Optional[int]:
        # Emit a STATE message every N records during incremental sync, not only at
        # stream end, so a killed sync resumes past what was already emitted.
        return 1000 if self._configured_cursor_field else None

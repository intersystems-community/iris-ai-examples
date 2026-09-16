"""Local publisher state: what has already been durably published.

This state file is NOT part of the Open Mirroring landing zone -- it is the
publisher's own bookkeeping, kept in a separate directory so it is never
mistaken by the Fabric mirroring engine for a data or metadata file inside
`Files/LandingZone/<table>/`.

State is written atomically (temp file + os.replace) on every update. The
write happens strictly *after* the corresponding landing-zone file has been
durably renamed into place, so a crash between "file written" and "state
updated" can only cause an at-least-once re-send of a change batch, never a
lost one and never a corrupted sequence number (sequence numbers are
independently re-derived from the landing zone directory itself -- see
`OpenMirroringLandingZoneWriter.next_sequence_number`).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TableState:
    snapshot_done: bool = False
    snapshot_offset: int = 0
    change_token: Optional[str] = None


class PublisherState:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._tables: dict[str, TableState] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            for name, t in raw.get("tables", {}).items():
                self._tables[name] = TableState(**t)

    def get(self, table_name: str) -> TableState:
        return self._tables.setdefault(table_name, TableState())

    def save(self) -> None:
        payload = {
            "tables": {
                name: {
                    "snapshot_done": t.snapshot_done,
                    "snapshot_offset": t.snapshot_offset,
                    "change_token": t.change_token,
                }
                for name, t in self._tables.items()
            }
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.path)

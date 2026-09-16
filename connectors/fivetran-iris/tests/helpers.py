"""Shared test doubles for sync tests."""

import copy


class RecordingOperations:
    """A `sync.SyncOperations` implementation that records every call
    instead of talking to the real Fivetran SDK, so tests can assert on
    exactly what would have been sent.

    `fail_after`, if set, raises `SimulatedCrash` on the N-th call across
    upsert/truncate/checkpoint combined (1-indexed) -- used to simulate an
    interrupted sync partway through and then resume from the last
    checkpointed state.
    """

    class SimulatedCrash(RuntimeError):
        pass

    def __init__(self, fail_after: int = None):
        self.upserts = []  # list of (table, data)
        self.truncates = []  # list of table
        self.checkpoints = []  # list of deep-copied state snapshots
        self.fail_after = fail_after
        self._call_count = 0

    def _tick(self):
        self._call_count += 1
        if self.fail_after is not None and self._call_count > self.fail_after:
            raise RecordingOperations.SimulatedCrash(
                f"simulated crash after {self.fail_after} operations"
            )

    def upsert(self, table: str, data: dict) -> None:
        self._tick()
        self.upserts.append((table, dict(data)))

    def truncate(self, table: str) -> None:
        self._tick()
        self.truncates.append(table)

    def checkpoint(self, state: dict) -> None:
        self._tick()
        self.checkpoints.append(copy.deepcopy(state))

    @property
    def last_checkpoint(self):
        return self.checkpoints[-1] if self.checkpoints else None

"""One native-API connection, serialised: a connection is one IRIS process."""

import threading


def _is_link_error(exc: Exception) -> bool:
    return "COMMUNICATION LINK ERROR" in str(exc).upper()


class IrisSession:
    def __init__(self, connect):
        self._connect = connect
        self._lock = threading.Lock()
        self._native = None

    def call(self, fn, *args):
        with self._lock:
            reused = self._native is not None
            try:
                return fn(self._ensure(), *args)
            except Exception as exc:
                self._native = None  # reconnect next time
                # After an IRIS restart the cached socket is dead; the request
                # never reached IRIS, so one retry on a fresh connection is safe.
                if not (reused and _is_link_error(exc)):
                    raise
            try:
                return fn(self._ensure(), *args)
            except Exception:
                self._native = None
                raise

    def _ensure(self):
        if self._native is None:
            self._native = self._connect()
        return self._native

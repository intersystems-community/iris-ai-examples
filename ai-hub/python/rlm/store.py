"""Session persistence seam — importable without iris_llm or IRIS."""

from __future__ import annotations

from typing import Dict, Optional, Tuple, Protocol, runtime_checkable


@runtime_checkable
class SessionStore(Protocol):
    def write(self, session_id: str, *path: str, value: str) -> None: ...
    def read(self, session_id: str, *path: str) -> Optional[str]: ...


class IRISStore:
    """Adapter that writes to ^RLM.Session IRIS globals."""

    def write(self, session_id: str, *path: str, value: str) -> None:
        try:
            import iris
            iris.gset("^RLM.Session", session_id, *path, value)
        except Exception:
            pass

    def read(self, session_id: str, *path: str) -> Optional[str]:
        try:
            import iris
            return iris.gget("^RLM.Session", session_id, *path) or None
        except Exception:
            return None


class InMemoryStore:
    """In-memory adapter for tests — no IRIS required."""

    def __init__(self) -> None:
        self._data: Dict[Tuple, str] = {}

    def write(self, session_id: str, *path: str, value: str) -> None:
        self._data[(session_id, *path)] = value

    def read(self, session_id: str, *path: str) -> Optional[str]:
        return self._data.get((session_id, *path))


def default_store() -> SessionStore:
    try:
        import iris  # noqa: F401
        return IRISStore()
    except ImportError:
        return InMemoryStore()

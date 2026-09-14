"""
Unit tests for the SessionStore seam in RLMToolSet.

These tests run without IRIS — they use InMemoryStore, which is the whole
point of the seam: persistence behaviour is testable offline.
"""

import importlib.util
import os
import pytest

# Import store module directly to avoid triggering iris_llm in python/rlm/__init__.py
_store_spec = importlib.util.spec_from_file_location(
    "rlm_store",
    os.path.join(os.path.dirname(__file__), "../../python/rlm/store.py"),
)
_store_mod = importlib.util.module_from_spec(_store_spec)
_store_spec.loader.exec_module(_store_mod)

InMemoryStore = _store_mod.InMemoryStore
IRISStore = _store_mod.IRISStore
SessionStore = _store_mod.SessionStore
_default_store = _store_mod.default_store


# ── helpers ───────────────────────────────────────────────────────────────────

def _can_import_rlm_toolset() -> bool:
    try:
        from python.rlm.toolset import RLMToolSet  # noqa: F401
        return True
    except Exception:
        return False


def _make_toolset(store=None):
    from unittest.mock import MagicMock
    from python.rlm.toolset import RLMToolSet
    provider = MagicMock()
    return RLMToolSet(
        context="test context",
        provider=provider,
        model="gpt-4o",
        store=store,
    )


_HAS_RLM = _can_import_rlm_toolset()


# ── InMemoryStore tests (no iris_llm needed) ──────────────────────────────────

class TestInMemoryStore:
    def test_write_and_read_roundtrip(self):
        s = InMemoryStore()
        s.write("sess1", "context", value="hello")
        assert s.read("sess1", "context") == "hello"

    def test_read_missing_returns_none(self):
        s = InMemoryStore()
        assert s.read("missing", "context") is None

    def test_nested_path(self):
        s = InMemoryStore()
        s.write("sess1", "metadata", "iterations", value="5")
        assert s.read("sess1", "metadata", "iterations") == "5"

    def test_overwrite(self):
        s = InMemoryStore()
        s.write("sess1", "context", value="v1")
        s.write("sess1", "context", value="v2")
        assert s.read("sess1", "context") == "v2"

    def test_different_sessions_isolated(self):
        s = InMemoryStore()
        s.write("a", "context", value="alpha")
        s.write("b", "context", value="beta")
        assert s.read("a", "context") == "alpha"
        assert s.read("b", "context") == "beta"

    def test_satisfies_protocol(self):
        assert isinstance(InMemoryStore(), SessionStore)


# ── RLMToolSet integration tests (require iris_llm) ───────────────────────────

@pytest.mark.skipif(not _HAS_RLM, reason="iris_llm not installed")
class TestRLMToolSetWithStore:
    """Smoke-test persistence paths via InMemoryStore. No IRIS required."""

    def test_persist_context_written_to_store(self):
        store = InMemoryStore()
        ts = _make_toolset(store=store)
        assert store.read(ts.session.session_id, "context") == ts.session.context

    def test_persist_metadata_written_to_store(self):
        store = InMemoryStore()
        ts = _make_toolset(store=store)
        ts._persist_metadata("custom_key", "custom_val")
        assert store.read(ts.session.session_id, "metadata", "custom_key") == "custom_val"

    def test_cleanup_expired_marks_store(self):
        from python.rlm.toolset import RLMToolSet
        from datetime import datetime, timezone, timedelta
        store = InMemoryStore()
        ts = _make_toolset(store=store)
        sid = ts.session.session_id
        future = datetime.now(timezone.utc) + timedelta(seconds=90000)
        RLMToolSet.cleanup_expired_sessions(ttl_seconds=1, now=future, store=store)
        assert store.read(sid, "metadata", "expired") == "true"

"""
Unit test conftest — mock heavy IRIS/ML dependencies so tests run without Docker.

Every stub here is conditional. A bare `sys.modules["iris"] = MagicMock()` at
import time is not scoped to this directory: pytest imports this file while
collecting the whole suite, so the mock survives into the e2e tests, and those
call `import iris` inside the test body. Measured with the stack up — five e2e
tests then asserted about a MagicMock against a live IRIS, including one that
expected bad credentials to raise, which a mock never does. Stub only what the
interpreter cannot already import.
"""
import importlib.util
import sys
from unittest.mock import MagicMock


def _absent(name: str) -> bool:
    """True when `import name` would fail, so a stub is the only way in."""
    if name in sys.modules:
        return False
    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ValueError):
        return True


def _stub_if_absent(name: str, module) -> None:
    if _absent(name):
        sys.modules[name] = module


# Mock intersystems_pyprod so production modules import cleanly
pyprod_mock = MagicMock()
pyprod_mock.BusinessService = object
pyprod_mock.BusinessProcess = object
pyprod_mock.BusinessOperation = object
pyprod_mock.Production = object
pyprod_mock.Status = MagicMock()
pyprod_mock.Message = object
_stub_if_absent("intersystems_pyprod", pyprod_mock)

# Mock iris (IRIS Native API) — not needed for unit logic tests, and never
# installed when the real one is, since e2e connects through it for real.
_stub_if_absent("iris", MagicMock())

# Mock langchain_intersystems
lc_mock = MagicMock()
_stub_if_absent("langchain_intersystems", lc_mock)
_stub_if_absent("langchain_intersystems.chat_models", lc_mock)

# Mock httpx so fhir_quality_agent imports without network
import httpx as _httpx  # noqa: keep real httpx available for tests that need it

# Mock plotly for ops_agent HTML report building
plotly_mock = MagicMock()
_stub_if_absent("plotly", plotly_mock)
_stub_if_absent("plotly.graph_objects", plotly_mock)
_stub_if_absent("plotly.subplots", plotly_mock)
_stub_if_absent("plotly.io", plotly_mock)

# Mock iris_llm for knowledge_tools
iris_llm_mock = MagicMock()
iris_llm_mock.ToolSet = object
iris_llm_mock.tool = lambda f: f  # pass-through decorator
_stub_if_absent("iris_llm", iris_llm_mock)

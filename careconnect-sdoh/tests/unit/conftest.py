"""
Unit test conftest — mock heavy IRIS/ML dependencies so tests run without Docker.
"""
import sys
from unittest.mock import MagicMock

# Mock intersystems_pyprod so production modules import cleanly
pyprod_mock = MagicMock()
pyprod_mock.BusinessService = object
pyprod_mock.BusinessProcess = object
pyprod_mock.BusinessOperation = object
pyprod_mock.Production = object
pyprod_mock.Status = MagicMock()
pyprod_mock.Message = object
sys.modules["intersystems_pyprod"] = pyprod_mock

# Mock iris (IRIS Native API) — not needed for unit logic tests
iris_mock = MagicMock()
sys.modules["iris"] = iris_mock

# Mock langchain_intersystems
lc_mock = MagicMock()
sys.modules["langchain_intersystems"] = lc_mock
sys.modules["langchain_intersystems.chat_models"] = lc_mock

# Mock httpx so fhir_quality_agent imports without network
import httpx as _httpx  # noqa: keep real httpx available for tests that need it

# Mock plotly for ops_agent HTML report building
plotly_mock = MagicMock()
sys.modules["plotly"] = plotly_mock
sys.modules["plotly.graph_objects"] = plotly_mock
sys.modules["plotly.subplots"] = plotly_mock
sys.modules["plotly.io"] = plotly_mock

# Mock iris_llm for knowledge_tools
iris_llm_mock = MagicMock()
iris_llm_mock.ToolSet = object
iris_llm_mock.tool = lambda f: f  # pass-through decorator
sys.modules["iris_llm"] = iris_llm_mock

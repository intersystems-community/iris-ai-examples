"""Unit tests for knowledge_tools — config constants and _bolt error paths. No IVG required."""
import pytest
from unittest.mock import patch, MagicMock
import httpx

pytestmark = pytest.mark.unit


class TestKnowledgeToolsConfig:
    def test_module_imports(self):
        import agents.knowledge_tools as kt
        assert kt is not None

    def test_unavailable_message_present(self):
        from agents.knowledge_tools import _UNAVAILABLE
        assert "ivg" in _UNAVAILABLE.lower() or "knowledge" in _UNAVAILABLE.lower()

    def test_default_port_is_8000(self):
        import agents.knowledge_tools as kt
        assert kt._IVG_PORT == 8000

    def test_default_api_key(self):
        import agents.knowledge_tools as kt
        assert kt._IVG_API_KEY == "changeme"

    def test_ivg_base_url_built_from_host_port(self):
        import agents.knowledge_tools as kt
        assert str(kt._IVG_PORT) in kt._IVG_BASE
        assert kt._IVG_HOST in kt._IVG_BASE


class TestBoltFunction:
    def test_bolt_raises_runtime_on_connect_error(self):
        from agents.knowledge_tools import _bolt
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(RuntimeError, match="unavailable|Knowledge"):
                _bolt("/api/knowledge/context", {"concept_id": "food_insecurity"})

    def test_bolt_raises_runtime_on_http_status_error(self):
        from agents.knowledge_tools import _bolt
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=mock_resp
        )
        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="500"):
                _bolt("/api/knowledge/context", {"concept_id": "food_insecurity"})

    def test_bolt_returns_json_on_success(self):
        from agents.knowledge_tools import _bolt
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"decisions": []}
        with patch("httpx.post", return_value=mock_resp):
            result = _bolt("/api/knowledge/context", {"concept_id": "food_insecurity"})
        assert result == {"decisions": []}

    def test_bolt_sends_api_key_header(self):
        from agents.knowledge_tools import _bolt, _IVG_API_KEY
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {}
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            _bolt("/api/test", {})
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["X-API-Key"] == _IVG_API_KEY


class TestKnowledgeToolsClass:
    def test_class_instantiates(self):
        from agents.knowledge_tools import KnowledgeTools
        kt = KnowledgeTools()
        assert kt is not None

    def test_system_prompt_addition_defined(self):
        import agents.knowledge_tools as mod
        assert hasattr(mod, "SYSTEM_PROMPT_ADDITION")
        assert "contradiction" in mod.SYSTEM_PROMPT_ADDITION.lower()

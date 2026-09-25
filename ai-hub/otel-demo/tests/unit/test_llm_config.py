"""One LLM setting for both tabs: OpenAI by default, any OpenAI-compatible server by URL."""

import json

from demo_app import llm_config


def test_default_is_openai_gpt_4o_mini():
    model, settings = llm_config.from_env({"OPENAI_API_KEY": "sk-x"})
    assert model == "gpt-4o-mini"
    assert json.loads(settings) == {"api_key": "sk-x"}


def test_a_base_url_points_the_openai_provider_elsewhere():
    model, settings = llm_config.from_env(
        {"DEMO_LLM_BASE_URL": "http://ollama:11434/v1", "DEMO_MODEL": "qwen2.5:14b"}
    )
    assert model == "qwen2.5:14b"
    assert json.loads(settings) == {"api_key": "unused", "base_url": "http://ollama:11434/v1"}


def test_an_empty_base_url_is_ignored():
    _, settings = llm_config.from_env({"OPENAI_API_KEY": "k", "DEMO_LLM_BASE_URL": ""})
    assert "base_url" not in json.loads(settings)

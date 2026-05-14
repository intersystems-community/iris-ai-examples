"""
Embedding provider abstraction for the PlanetCare demo.

Default: local sentence-transformers (all-MiniLM-L6-v2, 384-dim, no API key)
OpenAI: set EMBED_PROVIDER=openai and OPENAI_API_KEY
OpenRouter: set EMBED_PROVIDER=openrouter and OPENROUTER_API_KEY
Any OpenAI-compatible: set EMBED_BASE_URL to any endpoint

Usage:
    from setup.embedder import get_embedder
    embedder = get_embedder()
    vectors = embedder.embed(["some text", "another text"])
    print(embedder.dim)  # 384 or 1536
"""
import os
from typing import List


class LocalEmbedder:
    name = "all-MiniLM-L6-v2"
    dim = 384

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self.name)

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self._model.encode(texts, show_progress_bar=False).tolist()


class OpenAICompatibleEmbedder:
    def __init__(self, model: str, base_url: str, api_key: str, dim: int):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self.dim = dim
        self.name = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [e.embedding for e in resp.data]


def get_embedder():
    provider = os.getenv("EMBED_PROVIDER", "local").lower()

    if provider == "local":
        print("Embedder: local all-MiniLM-L6-v2 (384-dim, no API key needed)")
        return LocalEmbedder()

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY not set. Use EMBED_PROVIDER=local for no-key setup.")
        print("Embedder: OpenAI text-embedding-ada-002 (1536-dim)")
        return OpenAICompatibleEmbedder(
            model="text-embedding-ada-002",
            base_url="https://api.openai.com/v1",
            api_key=key,
            dim=1536,
        )

    if provider == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set.")
        model = os.getenv("EMBED_MODEL", "openai/text-embedding-ada-002")
        print(f"Embedder: OpenRouter {model} (1536-dim)")
        return OpenAICompatibleEmbedder(
            model=model,
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            dim=1536,
        )

    if provider == "custom":
        key = os.getenv("EMBED_API_KEY", "none")
        base_url = os.getenv("EMBED_BASE_URL", "")
        model = os.getenv("EMBED_MODEL", "text-embedding-ada-002")
        dim = int(os.getenv("EMBED_DIM", "1536"))
        if not base_url:
            raise ValueError("EMBED_BASE_URL not set for custom provider.")
        print(f"Embedder: custom {base_url} model={model} dim={dim}")
        return OpenAICompatibleEmbedder(model=model, base_url=base_url, api_key=key, dim=dim)

    raise ValueError(f"Unknown EMBED_PROVIDER={provider}. Use: local, openai, openrouter, custom")


def get_llm_client():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return None, None
        from openai import OpenAI
        return OpenAI(api_key=key), os.getenv("LLM_MODEL", "gpt-4o-mini")

    if provider == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY", "")
        from openai import OpenAI
        model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        return OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "https://github.com/intersystems-community/ready2026-knowledge-graph-demo"}
        ), model

    if provider == "custom":
        from openai import OpenAI
        return OpenAI(
            api_key=os.getenv("LLM_API_KEY", "none"),
            base_url=os.getenv("LLM_BASE_URL", ""),
        ), os.getenv("LLM_MODEL", "gpt-4o-mini")

    return None, None

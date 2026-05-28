"""
embedding_client — provider-agnostic embedding adapter.

Protocol:
    embed(text: str) -> list[float]
    embed_many(texts: list[str]) -> list[list[float]]

Supported providers (add new ones by implementing EmbeddingClient):
    OpenAIEmbeddingClient  — text-embedding-3-small (1536d)
    VoyageEmbeddingClient  — voyage-3-lite (512d)  [future]

Factory:
    create_embedding_client() — reads env config, returns best available client.
    Returns None if no provider is configured (memory block will skip embedding).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger(__name__)

OPENAI_DIMENSIONS = 1536
VOYAGE_DIMENSIONS = 512


@runtime_checkable
class EmbeddingClient(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...
    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingClient:
    """OpenAI text-embedding-3-small adapter."""

    dimensions = OPENAI_DIMENSIONS
    _MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={"model": self._MODEL, "input": texts},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()["data"]
        # API returns list sorted by index
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


class VoyageEmbeddingClient:
    """Voyage AI voyage-3-lite adapter (future)."""

    dimensions = VOYAGE_DIMENSIONS
    _MODEL = "voyage-3-lite"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx
        r = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={"model": self._MODEL, "input": texts},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


def create_embedding_client() -> EmbeddingClient | None:
    """Return the best available embedding client based on configured keys."""
    from app.core.config import settings
    if settings.openai_api_key:
        log.debug("embedding.provider", provider="openai")
        return OpenAIEmbeddingClient(settings.openai_api_key)
    if settings.voyage_api_key:
        log.debug("embedding.provider", provider="voyage")
        return VoyageEmbeddingClient(settings.voyage_api_key)
    log.warning("embedding.no_provider", msg="Set OPENAI_API_KEY or VOYAGE_API_KEY to enable memory block")
    return None

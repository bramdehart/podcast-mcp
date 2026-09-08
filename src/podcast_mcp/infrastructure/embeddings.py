"""Embedding infrastructure: OpenAI embedding client and pgvector helpers."""

from __future__ import annotations

import sys
from typing import Protocol

import requests

from podcast_mcp.config import settings


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def openai_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def embed_texts(texts: list[str], model: str, dimensions: int, batch_size: int) -> list[list[float]]:
    api_key = settings.require_openai_api_key()

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers=openai_headers(api_key),
            json={
                "model": model,
                "input": batch,
                "dimensions": dimensions,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings.extend(item["embedding"] for item in sorted(payload["data"], key=lambda item: item["index"]))
        print(f"Embedded {min(start + len(batch), len(texts))}/{len(texts)} chunks", file=sys.stderr, flush=True)

    return embeddings


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in values) + "]"


class OpenAIEmbeddingClient:
    """Embeddings backed by the OpenAI API, matching the configured model."""

    def __init__(
        self,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model = model or settings.embedding_model
        self.dimensions = dimensions or settings.embedding_dimensions
        self.batch_size = batch_size or settings.embedding_batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts, self.model, self.dimensions, self.batch_size)
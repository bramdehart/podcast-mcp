"""Infrastructure adapters for podcast_mcp."""

from podcast_mcp.infrastructure.embeddings import (
    EmbeddingClient,
    OpenAIEmbeddingClient,
    embed_texts,
    vector_literal,
)
from podcast_mcp.infrastructure.postgres import (
    PostgresTranscriptRepository,
    TranscriptRepository,
    database_url,
)

__all__ = [
    "EmbeddingClient",
    "OpenAIEmbeddingClient",
    "PostgresTranscriptRepository",
    "TranscriptRepository",
    "database_url",
    "embed_texts",
    "vector_literal",
]
"""The embedding seam: text -> retrieval vectors, behind a mockable interface."""

from __future__ import annotations

from plain_sight.embedding.provider import EmbeddingProvider, StubEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "StubEmbeddingProvider",
]

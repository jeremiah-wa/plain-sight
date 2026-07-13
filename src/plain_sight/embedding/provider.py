"""The ``EmbeddingProvider`` seam: text -> a fixed-width retrieval embedding.

Embedding is the one place a live embedding model would be consulted, and like
the :class:`~plain_sight.extraction.Extractor` it lives entirely behind this
interface so tests drive similarity deterministically with a stub, never a
network or a nondeterministic model. Vectors are for retrieval and entity-assist
(semantic/fuzzy matching, query-time similarity), never for generation.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from plain_sight.db.postgres import EMBEDDING_DIMENSIONS


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns a piece of text (a counterparty label, or a search query) into a vector."""

    def embed(self, text: str) -> list[float]:
        """Return an embedding of ``text`` with :data:`EMBEDDING_DIMENSIONS` entries."""
        ...


class StubEmbeddingProvider:
    """A deterministic test double for the embedding boundary.

    Two ways to control what it returns, so a test can make "near" and "far"
    meaningful without a live model:

    * ``vectors`` pins specific strings to specific embeddings (exact match).
    * anything else is hashed to a stable pseudo-random unit-ish vector, so the
      same text always embeds to the same point and distinct text to a different
      one. This is deterministic, not semantic, which is why tests that assert
      *ranking* pin the vectors explicitly.
    """

    def __init__(
        self,
        *,
        vectors: Mapping[str, Sequence[float]] | None = None,
        dimensions: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        self._dimensions = dimensions
        self._vectors = {text: [float(v) for v in vec] for text, vec in (vectors or {}).items()}

    def embed(self, text: str) -> list[float]:
        pinned = self._vectors.get(text)
        if pinned is not None:
            return list(pinned)
        return self._hashed(text)

    def _hashed(self, text: str) -> list[float]:
        vector: list[float] = []
        counter = 0
        while len(vector) < self._dimensions:
            digest = hashlib.sha256(f"{text}:{counter}".encode()).digest()
            for i in range(0, len(digest), 4):
                if len(vector) >= self._dimensions:
                    break
                # Map four bytes to a signed value in roughly [-1, 1).
                chunk = int.from_bytes(digest[i : i + 4], "big")
                vector.append(chunk / 2**31 - 1.0)
            counter += 1
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]

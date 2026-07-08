"""Extraction: the mockable model seam plus the candidate -> event mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plain_sight.extraction.extractor import Extractor, StubExtractor
from plain_sight.extraction.mapping import map_candidates, normalise_counterparty

if TYPE_CHECKING:
    from plain_sight.extraction.claude import ClaudeExtractor

__all__ = [
    "ClaudeExtractor",
    "Extractor",
    "StubExtractor",
    "map_candidates",
    "normalise_counterparty",
]


def __getattr__(name: str) -> Any:
    # Import the live extractor lazily so the core package (and the test suite)
    # never requires the optional ``anthropic`` dependency.
    if name == "ClaudeExtractor":
        from plain_sight.extraction.claude import ClaudeExtractor

        return ClaudeExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

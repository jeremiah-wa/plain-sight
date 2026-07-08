"""The ``Extractor`` seam: raw source document bytes -> candidate declarations.

Extraction is the one place a live multimodal model is consulted. It lives
entirely behind this interface (model id is config-driven) so tests mock the
boundary and assert normalisation and provenance deterministically, with no live
network and no LLM nondeterminism.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from plain_sight.domain import ExtractionResult, SourceDocument


@runtime_checkable
class Extractor(Protocol):
    """Turns one stored source document into structured candidate declarations."""

    def extract(self, document: SourceDocument, content: bytes) -> ExtractionResult:
        """Return candidate declarations with per-field page and confidence."""
        ...


class StubExtractor:
    """A test double that returns a fixed :class:`ExtractionResult`.

    Stands in for the real model at the extraction boundary so the pipeline can
    be driven end-to-end against a checked-in scan without a network or an LLM.
    """

    def __init__(self, result: ExtractionResult) -> None:
        self._result = result

    def extract(self, document: SourceDocument, content: bytes) -> ExtractionResult:
        return self._result

"""Domain types, validated with Pydantic at the boundaries only (not persistence)."""

from __future__ import annotations

from plain_sight.domain.models import (
    BBox,
    CandidateDeclaration,
    ClaimCorrection,
    Counterparty,
    DeclarationEvent,
    ExtractionResult,
    InterestCategory,
    Person,
    Provenance,
    SourceDocument,
    VerificationStatus,
)

__all__ = [
    "BBox",
    "CandidateDeclaration",
    "ClaimCorrection",
    "Counterparty",
    "DeclarationEvent",
    "ExtractionResult",
    "InterestCategory",
    "Person",
    "Provenance",
    "SourceDocument",
    "VerificationStatus",
]

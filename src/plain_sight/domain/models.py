"""Domain types for the walking skeleton.

These are validated with Pydantic *at the boundaries only* (extractor output,
CLI input, database rows crossing back into the application), never used as a
persistence layer. The database is `psycopg` v3 + hand-written SQL.

The vocabulary here mirrors ``docs/GLOSSARY.md``: a **declaration event** is the
atomic, per-claim unit of record; every event carries **per-claim provenance**
and starts ``pending`` until a human **verifies** it. A **provisional
counterparty** is a first-class entity referenced by UUID, never inlined as a
bare string on an event.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# A page-relative bounding box, ``(x0, y0, x1, y1)``. Optional and operator-assisted:
# the extractor returns the page it read a field from, but never fabricates pixel
# coordinates, so ``bbox`` is ``None`` unless a human supplies it later.
BBox = tuple[float, float, float, float]


class VerificationStatus(StrEnum):
    """Per-claim review state. Only ``verified`` claims are ever displayed."""

    PENDING = "pending"
    VERIFIED = "verified"


class InterestCategory(StrEnum):
    """The kind of declared interest. Kept deliberately small for the skeleton."""

    SHAREHOLDING = "shareholding"
    DIRECTORSHIP = "directorship"
    REAL_ESTATE = "real_estate"
    GIFT = "gift"
    SPONSORED_TRAVEL = "sponsored_travel"
    TRUST = "trust"
    LIABILITY = "liability"
    OTHER = "other"


class Provenance(BaseModel):
    """Where a single claim came from, and how far it has been trusted.

    Provenance is *per claim*, not per document: every declaration event points
    back at the exact source document, page, extraction method, and the model's
    self-reported confidence, plus when the source bytes were fetched.
    """

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    page: int = Field(ge=1)
    extraction_method: str = Field(min_length=1)
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    fetch_timestamp: datetime
    bbox: BBox | None = None


class Person(BaseModel):
    """A parliamentarian, hard-resolved to external authorities where possible.

    Politicians get canonical identity (``canonical_name`` + ``name_variants`` +
    ``external_ids`` such as Parliament/OpenAustralia/Wikidata IDs) so the same
    member can be tracked across parliaments. The skeleton only populates what it
    needs, but the shape is here so later slices don't re-model it.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    canonical_name: str = Field(min_length=1)
    name_variants: list[str] = Field(default_factory=list)
    external_ids: dict[str, str] = Field(default_factory=dict)
    chamber: str | None = None
    jurisdiction: str = "AU:federal"


class Counterparty(BaseModel):
    """A company/trust/asset named in a declaration: a **provisional** entity.

    Stored with a stable opaque UUID, the raw transcribed string, and a
    normalised label, and explicitly marked ``resolved = False``. v1 never
    asserts a legal identity (e.g. an ACN) for it; the UUID is the anchor that v2
    resolution attaches to. Declaration events reference this by ``id``, never by
    inlining ``raw_string``.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    raw_string: str = Field(min_length=1)
    normalised_label: str = Field(min_length=1)
    resolved: bool = False


class SourceDocument(BaseModel):
    """The immutable source PDF, the provenance anchor for every claim from it."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    member_id: UUID
    content_sha256: str = Field(min_length=64, max_length=64)
    storage_path: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    source_url: str | None = None
    fetched_at: datetime
    jurisdiction: str = "AU:federal"


class CandidateDeclaration(BaseModel):
    """One candidate claim emitted by an :class:`~plain_sight.extraction.Extractor`.

    This is the structured-output boundary: the model returns a raw counterparty
    string, the interest category, optional effective dates, the page it read the
    claim from, and its own confidence. No free-text parsing happens downstream.
    """

    model_config = ConfigDict(frozen=True)

    category: InterestCategory
    counterparty_raw: str = Field(min_length=1)
    description: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    page: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBox | None = None


class ExtractionResult(BaseModel):
    """The full structured output of one extraction run over one document."""

    model_config = ConfigDict(frozen=True)

    method: str = Field(min_length=1)
    candidates: list[CandidateDeclaration] = Field(default_factory=list)


class DeclarationEvent(BaseModel):
    """A stored, per-claim declaration event: the atomic unit of record.

    References its counterparty by UUID, carries a complete :class:`Provenance`
    pointer, and starts ``pending`` until a human confirms it.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    member_id: UUID
    counterparty_id: UUID
    category: InterestCategory
    description: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    provenance: Provenance
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verified_by: str | None = None
    verified_at: datetime | None = None
    ingested_at: datetime

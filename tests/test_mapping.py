"""Seam 1: normalised candidate declarations map to stored declaration events.

This is the highest-value seam (PRD testing decisions §1): a pure function from a
stored document + extraction result to counterparties and declaration events,
with per-claim provenance. No network, no LLM, no database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID

from plain_sight.domain import (
    CandidateDeclaration,
    ExtractionResult,
    InterestCategory,
    SourceDocument,
    VerificationStatus,
)
from plain_sight.extraction import map_candidates, normalise_counterparty

FETCHED_AT = datetime(2026, 7, 1, 9, 30, tzinfo=UTC)
INGESTED_AT = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
DOCUMENT_ID = UUID(int=0xD0C)
MEMBER_ID = UUID(int=0xE)


def _document() -> SourceDocument:
    return SourceDocument(
        id=DOCUMENT_ID,
        member_id=MEMBER_ID,
        content_sha256="a" * 64,
        storage_path="data/documents/aaaa.pdf",
        page_count=2,
        source_url="https://example.test/register.pdf",
        fetched_at=FETCHED_AT,
    )


def test_normalise_counterparty_collapses_whitespace() -> None:
    assert normalise_counterparty("  BHP   Group  Ltd \n") == "BHP Group Ltd"


def test_map_emits_pending_events_with_per_claim_provenance(
    id_factory: Callable[[], UUID],
) -> None:
    document = _document()
    result = ExtractionResult(
        method="stub-extractor",
        candidates=[
            CandidateDeclaration(
                category=InterestCategory.SHAREHOLDING,
                counterparty_raw="BHP Group Ltd",
                description="500 ordinary shares",
                valid_from=date(2025, 3, 1),
                page=1,
                confidence=0.91,
            ),
        ],
    )

    counterparties, events = map_candidates(
        document, result, ingested_at=INGESTED_AT, id_factory=id_factory
    )

    assert len(events) == 1
    event = events[0]
    assert event.member_id == MEMBER_ID
    assert event.category is InterestCategory.SHAREHOLDING
    assert event.valid_from == date(2025, 3, 1)
    assert event.verification_status is VerificationStatus.PENDING
    assert event.verified_by is None
    # Per-claim provenance points back at the exact source, page, method, confidence.
    assert event.provenance.document_id == DOCUMENT_ID
    assert event.provenance.page == 1
    assert event.provenance.extraction_method == "stub-extractor"
    assert event.provenance.extraction_confidence == 0.91
    assert event.provenance.fetch_timestamp == FETCHED_AT
    assert event.provenance.bbox is None
    # The counterparty is a first-class entity referenced by UUID.
    assert len(counterparties) == 1
    assert event.counterparty_id == counterparties[0].id
    assert counterparties[0].resolved is False


def test_map_references_counterparty_by_uuid_and_dedupes(
    id_factory: Callable[[], UUID],
) -> None:
    document = _document()
    result = ExtractionResult(
        method="stub-extractor",
        candidates=[
            CandidateDeclaration(
                category=InterestCategory.SHAREHOLDING,
                counterparty_raw="BHP Group Ltd",
                page=1,
                confidence=0.9,
            ),
            CandidateDeclaration(
                category=InterestCategory.DIRECTORSHIP,
                counterparty_raw="  bhp   group ltd ",  # same entity, messy transcription
                page=2,
                confidence=0.7,
            ),
            CandidateDeclaration(
                category=InterestCategory.REAL_ESTATE,
                counterparty_raw="Acme Trust",
                page=2,
                confidence=0.6,
            ),
        ],
    )

    counterparties, events = map_candidates(
        document, result, ingested_at=INGESTED_AT, id_factory=id_factory
    )

    # Two distinct counterparties for three claims; the messy duplicate collapses.
    assert len(counterparties) == 2
    assert {cp.normalised_label for cp in counterparties} == {"BHP Group Ltd", "Acme Trust"}
    bhp_events = [e for e in events if e.category is not InterestCategory.REAL_ESTATE]
    assert {e.counterparty_id for e in bhp_events} == {counterparties[0].id}
    # No bare counterparty string is inlined on an event: the model has no such field.
    assert not hasattr(events[0], "counterparty_raw")
    # Every event references a counterparty that was actually emitted.
    emitted_ids = {cp.id for cp in counterparties}
    assert all(e.counterparty_id in emitted_ids for e in events)

"""The walking skeleton, driven end to end with a stub extractor.

Stored PDF → extract (stub) → declaration events → confirm → text display, with
an in-memory repository and the real document store. No network, no LLM, no
database. Asserts the two highest-risk behaviours directly: a pending claim
never reaches the display, and a verified claim carries its provenance to it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from plain_sight import service
from plain_sight.db import InMemoryRepository
from plain_sight.domain import (
    CandidateDeclaration,
    ExtractionResult,
    InterestCategory,
)
from plain_sight.extraction import StubExtractor
from plain_sight.sources import DocumentStore

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


def _extraction() -> ExtractionResult:
    return ExtractionResult(
        method="stub-extractor",
        candidates=[
            CandidateDeclaration(
                category=InterestCategory.SHAREHOLDING,
                counterparty_raw="BHP Group Ltd",
                description="500 ordinary shares",
                valid_from=date(2025, 3, 1),
                page=1,
                confidence=0.92,
            ),
            CandidateDeclaration(
                category=InterestCategory.REAL_ESTATE,
                counterparty_raw="Acme Trust",
                page=1,
                confidence=0.4,
            ),
        ],
    )


def test_pipeline_confirms_one_claim_and_displays_only_verified(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)
    extractor = StubExtractor(_extraction())

    events = service.ingest(
        repo=repo,
        store=store,
        extractor=extractor,
        member_name="Jane Member",
        pdf_bytes=sample_pdf_bytes,
        now=NOW,
        source_url="https://example.test/register.pdf",
        id_factory=id_factory,
    )
    assert len(events) == 2
    assert all(e.verification_status.value == "pending" for e in events)

    # Nothing is verified yet, so nothing is displayed.
    before = service.render_member_interests(repo=repo, member_name="Jane Member")
    assert "no verified declared interests" in before
    assert "BHP" not in before

    # The crude confirm flips exactly one claim to verified.
    shareholding = next(e for e in events if e.category is InterestCategory.SHAREHOLDING)
    assert service.confirm(
        repo=repo, event_id=shareholding.id, verified_by="operator", verified_at=NOW
    )

    after = service.render_member_interests(repo=repo, member_name="Jane Member")
    # The verified claim appears, "as declared", with its provenance pointer.
    assert 'as declared: "BHP Group Ltd"' in after
    assert str(shareholding.provenance.document_id) in after
    assert "page 1" in after
    assert "verified by operator" in after
    # The still-pending claim is physically absent from the display.
    assert "Acme Trust" not in after


def test_confirm_is_idempotent_and_guards_unknown_ids(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)
    events = service.ingest(
        repo=repo,
        store=store,
        extractor=StubExtractor(_extraction()),
        member_name="Jane Member",
        pdf_bytes=sample_pdf_bytes,
        now=NOW,
        id_factory=id_factory,
    )

    assert service.confirm(repo=repo, event_id=events[0].id, verified_by="op", verified_at=NOW)
    # Confirming an already-verified claim is a no-op.
    assert not service.confirm(repo=repo, event_id=events[0].id, verified_by="op", verified_at=NOW)
    # Confirming an unknown id does nothing.
    assert not service.confirm(
        repo=repo, event_id=UUID(int=0xDEAD), verified_by="op", verified_at=NOW
    )

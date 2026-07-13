"""The read/write seam beneath the verification UI, driven in memory.

Per the PRD, the verification UI is validated by exercising the seam beneath it
(confirm/correct produce the right events), not by UI snapshot tests. These tests
seed pending claims and assert the events emitted by ``confirm`` and ``correct``:

- **confirm** transitions a pending claim to ``verified`` with verification
  metadata (``verified_by`` / ``verified_at``);
- **correct** appends a superseding event carrying who/why/when, and the original
  machine candidate is retained in the log, marked superseded, never mutated.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID

from plain_sight import service
from plain_sight.db import InMemoryRepository
from plain_sight.domain import (
    ClaimCorrection,
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    Provenance,
    SourceDocument,
    VerificationStatus,
)

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 9, 9, 30, tzinfo=UTC)

MEMBER_ID = UUID(int=0xA1)
DOCUMENT_ID = UUID(int=0xD0)


def _seed_pending_claim(
    repo: InMemoryRepository,
    id_factory: Callable[[], UUID],
    *,
    counterparty_raw: str = "BHP Group Ltd",
    category: InterestCategory = InterestCategory.SHAREHOLDING,
    confidence: float = 0.42,
) -> DeclarationEvent:
    """Seed one member, document, counterparty, and a single pending event."""

    repo.add_person(Person(id=MEMBER_ID, canonical_name="Jane Member"))
    repo.add_source_document(
        SourceDocument(
            id=DOCUMENT_ID,
            member_id=MEMBER_ID,
            content_sha256="0" * 64,
            storage_path="documents/jane.pdf",
            page_count=1,
            fetched_at=NOW,
        )
    )
    counterparty_id = id_factory()
    repo.add_counterparty(
        Counterparty(
            id=counterparty_id,
            raw_string=counterparty_raw,
            normalised_label=counterparty_raw,
        )
    )
    event = DeclarationEvent(
        id=id_factory(),
        member_id=MEMBER_ID,
        counterparty_id=counterparty_id,
        category=category,
        description="500 ordinary shares",
        valid_from=date(2025, 3, 1),
        provenance=Provenance(
            document_id=DOCUMENT_ID,
            page=1,
            extraction_method="stub-extractor",
            extraction_confidence=confidence,
            fetch_timestamp=NOW,
        ),
        verification_status=VerificationStatus.PENDING,
        ingested_at=NOW,
    )
    repo.add_declaration_event(event)
    return event


def test_confirm_emits_a_verified_event_with_metadata(
    id_factory: Callable[[], UUID],
) -> None:
    repo = InMemoryRepository()
    pending = _seed_pending_claim(repo, id_factory)

    assert service.confirm(
        repo=repo, event_id=pending.id, verified_by="operator", verified_at=LATER
    )

    stored = repo.get_declaration_event(pending.id)
    assert stored is not None
    assert stored.verification_status is VerificationStatus.VERIFIED
    assert stored.verified_by == "operator"
    assert stored.verified_at == LATER
    # Confirm-as-is never supersedes: the candidate is the record, now verified.
    assert stored.superseded_by is None


def test_correct_appends_a_superseding_event_and_retains_the_original(
    id_factory: Callable[[], UUID],
) -> None:
    repo = InMemoryRepository()
    original = _seed_pending_claim(repo, id_factory, category=InterestCategory.SHAREHOLDING)

    # The operator corrects the miscategorised claim and confirms it.
    successor = service.correct(
        repo=repo,
        event_id=original.id,
        correction=ClaimCorrection(
            category=InterestCategory.DIRECTORSHIP,
            counterparty_raw="BHP Group Ltd",
            description="500 ordinary shares",
            valid_from=date(2025, 3, 1),
        ),
        corrected_by="operator",
        corrected_at=LATER,
        reason="category was shareholding; register lists a directorship",
        id_factory=id_factory,
    )
    assert successor is not None

    # The superseding event carries the correction and the who/why/when.
    assert successor.id != original.id
    assert successor.category is InterestCategory.DIRECTORSHIP
    assert successor.verification_status is VerificationStatus.VERIFIED
    assert successor.verified_by == "operator"
    assert successor.verified_at == LATER
    assert successor.correction_reason == "category was shareholding; register lists a directorship"
    assert successor.superseded_by is None
    # Provenance is carried forward: the correction still points at the source scan.
    assert successor.provenance.document_id == original.provenance.document_id
    assert successor.provenance.page == original.provenance.page

    # The original machine candidate is retained, unmutated, and marked superseded.
    retained = repo.get_declaration_event(original.id)
    assert retained is not None
    assert retained.category is InterestCategory.SHAREHOLDING  # not mutated
    assert retained.verification_status is VerificationStatus.PENDING  # not mutated
    assert retained.superseded_by == successor.id  # points at its replacement


def test_correcting_the_counterparty_string_references_a_new_entity_by_uuid(
    id_factory: Callable[[], UUID],
) -> None:
    repo = InMemoryRepository()
    original = _seed_pending_claim(repo, id_factory, counterparty_raw="BPH Group Ltd")

    successor = service.correct(
        repo=repo,
        event_id=original.id,
        correction=ClaimCorrection(
            category=original.category,
            counterparty_raw="BHP Group Ltd",  # fix the transcription typo
            description=original.description,
            valid_from=original.valid_from,
        ),
        corrected_by="operator",
        corrected_at=LATER,
        reason="transcription typo BPH -> BHP",
        id_factory=id_factory,
    )
    assert successor is not None

    # The corrected string is a new first-class counterparty, referenced by UUID,
    # never inlined; the original counterparty is retained unchanged.
    assert successor.counterparty_id != original.counterparty_id
    new_cp = repo.get_counterparty(successor.counterparty_id)
    assert new_cp is not None
    assert new_cp.raw_string == "BHP Group Ltd"
    old_cp = repo.get_counterparty(original.counterparty_id)
    assert old_cp is not None
    assert old_cp.raw_string == "BPH Group Ltd"


def test_correct_refuses_an_already_verified_or_unknown_claim(
    id_factory: Callable[[], UUID],
) -> None:
    repo = InMemoryRepository()
    pending = _seed_pending_claim(repo, id_factory)
    correction = ClaimCorrection(
        category=InterestCategory.DIRECTORSHIP,
        counterparty_raw="BHP Group Ltd",
    )

    assert service.confirm(repo=repo, event_id=pending.id, verified_by="op", verified_at=NOW)
    # A confirmed claim is settled: correction refuses rather than double-writing.
    assert (
        service.correct(
            repo=repo,
            event_id=pending.id,
            correction=correction,
            corrected_by="op",
            corrected_at=LATER,
            reason="too late",
            id_factory=id_factory,
        )
        is None
    )
    # An unknown id yields nothing.
    assert (
        service.correct(
            repo=repo,
            event_id=UUID(int=0xDEAD),
            correction=correction,
            corrected_by="op",
            corrected_at=LATER,
            reason="nope",
            id_factory=id_factory,
        )
        is None
    )


def test_pending_claims_for_member_feed_the_ui_and_exclude_settled_claims(
    id_factory: Callable[[], UUID],
) -> None:
    repo = InMemoryRepository()
    pending = _seed_pending_claim(repo, id_factory)

    # A pending claim is offered to the operator, paired with its counterparty and
    # the source document the scan crop is rendered from.
    queue = repo.pending_claims_for_member(MEMBER_ID)
    assert len(queue) == 1
    event, counterparty, document = queue[0]
    assert event.id == pending.id
    assert counterparty.id == pending.counterparty_id
    assert document.id == DOCUMENT_ID

    # Once confirmed it leaves the queue: the operator only ever sees open work.
    assert service.confirm(repo=repo, event_id=pending.id, verified_by="op", verified_at=LATER)
    assert repo.pending_claims_for_member(MEMBER_ID) == []

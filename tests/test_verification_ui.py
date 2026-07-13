"""The verification UI driven over HTTP against the in-memory seam.

Per the PRD the UI is validated by exercising the read/write seam beneath it, not
by UI snapshot assertions: these tests POST to the real FastAPI routes and assert
the *events* that result (confirm produces a verified event; correct appends a
superseding event and retains the original). The one GET assertion is a smoke
check that the scan is placed beside the fields, not a rendered-HTML snapshot.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from plain_sight.db import InMemoryRepository
from plain_sight.db.repository import Repository
from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    Provenance,
    SourceDocument,
    VerificationStatus,
)
from plain_sight.web import create_app

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 9, 9, 30, tzinfo=UTC)

MEMBER = "Jane Member"
MEMBER_ID = UUID(int=0xA1)
DOCUMENT_ID = UUID(int=0xD0)
COUNTERPARTY_ID = UUID(int=0xC0)
EVENT_ID = UUID(int=0xE0)


def _seed(repo: InMemoryRepository) -> DeclarationEvent:
    repo.add_person(Person(id=MEMBER_ID, canonical_name=MEMBER))
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
    repo.add_counterparty(
        Counterparty(
            id=COUNTERPARTY_ID, raw_string="BHP Group Ltd", normalised_label="BHP Group Ltd"
        )
    )
    event = DeclarationEvent(
        id=EVENT_ID,
        member_id=MEMBER_ID,
        counterparty_id=COUNTERPARTY_ID,
        category=InterestCategory.SHAREHOLDING,
        description="500 ordinary shares",
        valid_from=date(2025, 3, 1),
        provenance=Provenance(
            document_id=DOCUMENT_ID,
            page=1,
            extraction_method="stub-extractor",
            extraction_confidence=0.42,
            fetch_timestamp=NOW,
        ),
        ingested_at=NOW,
    )
    repo.add_declaration_event(event)
    return event


def _client(repo: InMemoryRepository) -> TestClient:
    @contextmanager
    def session_factory() -> Iterator[Repository]:
        yield repo

    app = create_app(
        session_factory=session_factory,
        read_document=lambda _document: b"%PDF-1.4 fake scan",
        operator="op",
        clock=lambda: LATER,
    )
    return TestClient(app)


def test_detail_places_the_scan_beside_the_extracted_fields() -> None:
    repo = InMemoryRepository()
    _seed(repo)
    client = _client(repo)

    page = client.get(f"/members/{MEMBER}/claims/{EVENT_ID}")

    assert page.status_code == 200
    # The scan crop is embedded beside the fields, and the fields are present.
    assert f"/documents/{DOCUMENT_ID}" in page.text
    assert "BHP Group Ltd" in page.text

    scan = client.get(f"/documents/{DOCUMENT_ID}")
    assert scan.status_code == 200
    assert scan.headers["content-type"] == "application/pdf"
    assert scan.content == b"%PDF-1.4 fake scan"


def test_confirm_route_verifies_the_claim() -> None:
    repo = InMemoryRepository()
    _seed(repo)
    client = _client(repo)

    response = client.post(f"/members/{MEMBER}/claims/{EVENT_ID}/confirm")
    assert response.status_code == 200  # redirect followed to the queue

    settled = repo.get_declaration_event(EVENT_ID)
    assert settled is not None
    assert settled.verification_status is VerificationStatus.VERIFIED
    assert settled.verified_by == "op"
    assert settled.verified_at == LATER
    assert settled.superseded_by is None


def test_correct_route_supersedes_with_a_new_verified_event() -> None:
    repo = InMemoryRepository()
    _seed(repo)
    client = _client(repo)

    response = client.post(
        f"/members/{MEMBER}/claims/{EVENT_ID}/correct",
        data={
            "category": InterestCategory.DIRECTORSHIP.value,
            "counterparty_raw": "BHP Group Ltd",
            "description": "500 ordinary shares",
            "valid_from": "2025-03-01",
            "valid_to": "",
            "reason": "register lists a directorship, not a shareholding",
        },
    )
    assert response.status_code == 200

    # The original is retained, unmutated, and marked superseded.
    original = repo.get_declaration_event(EVENT_ID)
    assert original is not None
    assert original.category is InterestCategory.SHAREHOLDING
    assert original.verification_status is VerificationStatus.PENDING
    assert original.superseded_by is not None

    # The successor carries the correction plus the who/why/when.
    successor = repo.get_declaration_event(original.superseded_by)
    assert successor is not None
    assert successor.category is InterestCategory.DIRECTORSHIP
    assert successor.verification_status is VerificationStatus.VERIFIED
    assert successor.verified_by == "op"
    assert successor.verified_at == LATER
    assert successor.correction_reason == "register lists a directorship, not a shareholding"
    assert successor.provenance.document_id == DOCUMENT_ID


def test_confirm_route_is_idempotent_on_a_settled_claim() -> None:
    repo = InMemoryRepository()
    _seed(repo)
    client = _client(repo)

    assert client.post(f"/members/{MEMBER}/claims/{EVENT_ID}/confirm").status_code == 200
    # A second confirm writes nothing: the claim is already verified.
    assert client.post(f"/members/{MEMBER}/claims/{EVENT_ID}/confirm").status_code == 200
    settled = repo.get_declaration_event(EVENT_ID)
    assert settled is not None
    assert settled.verified_at == LATER

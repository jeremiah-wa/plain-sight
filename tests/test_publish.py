"""The publish gate: seeded repository → static HTML, verified-only.

Drives the publish seam (PRD seam 3) with an in-memory repository standing in
for Postgres: seed mixed verified/pending claims, run publish, and assert
against the *emitted HTML*, never a live query. The highest-risk behaviour the
PRD mandates a dedicated test for is asserted directly: a pending claim is
physically absent from the artifact, not merely hidden by a filter.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from plain_sight import publish, service
from plain_sight.db import InMemoryRepository
from plain_sight.domain import (
    CandidateDeclaration,
    ExtractionResult,
    InterestCategory,
)
from plain_sight.extraction import StubExtractor
from plain_sight.sources import DocumentStore

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)


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


def _seed(
    repo: InMemoryRepository,
    store: DocumentStore,
    sample_pdf_bytes: bytes,
    id_factory: Callable[[], UUID],
) -> None:
    """Ingest two pending claims and confirm exactly one (the shareholding)."""

    events = service.ingest(
        repo=repo,
        store=store,
        extractor=StubExtractor(_extraction()),
        member_name="Jane Member",
        pdf_bytes=sample_pdf_bytes,
        now=NOW,
        source_url="https://example.test/register.pdf",
        id_factory=id_factory,
    )
    shareholding = next(e for e in events if e.category is InterestCategory.SHAREHOLDING)
    service.confirm(repo=repo, event_id=shareholding.id, verified_by="operator", verified_at=NOW)


def test_publish_emits_verified_only_html(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)
    _seed(repo, store, sample_pdf_bytes, id_factory)

    html = publish.render_member_page(
        repo=repo, member_name="Jane Member", generated_at=GENERATED_AT
    )

    # The verified claim is present, rendered "as declared".
    assert 'as declared: "BHP Group Ltd"' in html
    # The still-pending claim is *physically absent* from the artifact.
    assert "Acme Trust" not in html


def test_published_claim_carries_source_link_and_confidence(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)
    _seed(repo, store, sample_pdf_bytes, id_factory)

    html = publish.render_member_page(
        repo=repo, member_name="Jane Member", generated_at=GENERATED_AT
    )

    # Links to the exact source page/scan the claim came from.
    assert 'href="https://example.test/register.pdf#page=1"' in html
    # A per-claim confidence indication is shown.
    assert "0.92" in html


def test_published_page_renders_freshness_and_standing_statement(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)
    _seed(repo, store, sample_pdf_bytes, id_factory)

    html = publish.render_member_page(
        repo=repo, member_name="Jane Member", generated_at=GENERATED_AT
    )

    # Per-member freshness block: source last checked / changed, last verified by us.
    assert "source last checked" in html
    assert "source last changed" in html
    assert "last verified" in html
    # The freshness dates themselves are rendered.
    assert "2026-07-08" in html  # source fetched / last verified

    # The standing statement and the "as declared" framing.
    assert "mirrors the official record" in html
    assert "asserts no connections" in html


def test_publish_writes_html_file_to_output_dir(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    repo = InMemoryRepository()
    store = DocumentStore(tmp_path / "docs")
    _seed(repo, store, sample_pdf_bytes, id_factory)

    out = tmp_path / "site"
    path = publish.publish_member(
        repo=repo, member_name="Jane Member", output_dir=out, generated_at=GENERATED_AT
    )

    assert path.exists()
    assert path.parent == out
    written = path.read_text()
    assert 'as declared: "BHP Group Ltd"' in written
    assert "Acme Trust" not in written

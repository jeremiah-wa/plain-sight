"""Change detection: a re-poll of an unchanged PDF is free; a changed one flags work.

PRD seam 4, driven with local document fixtures and no live network: the same
one-page scan re-polled yields no work, a re-rendered (same page count, different
bytes) copy is a hash change, and a grown copy is a page-count increase. Both
changed cases flag the member for re-extraction; the unchanged case does not.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader, PdfWriter

from plain_sight.db import InMemoryRepository
from plain_sight.domain import SourceDocument
from plain_sight.monitoring import (
    ChangeReason,
    assess_document,
    fingerprint,
    poll_member,
)
from plain_sight.sources import DocumentStore

MEMBER_ID = UUID(int=0xA11CE)
FETCHED_AT = datetime(2026, 7, 1, 9, 30, tzinfo=UTC)


def _rerendered(pdf_bytes: bytes) -> bytes:
    """A byte-different but same-page-count copy: an in-place revision."""

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({"/Producer": "plain-sight-test-rerender"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _grown(pdf_bytes: bytes) -> bytes:
    """A copy with an extra appended page: a page-count increase."""

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_page(reader.pages[0])  # an appended alteration/continuation page
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_unchanged_document_yields_no_work(sample_pdf_bytes: bytes) -> None:
    reader = PdfReader(io.BytesIO(sample_pdf_bytes))
    stored = _stored(sample_pdf_bytes, page_count=len(reader.pages))

    assessment = assess_document(stored, sample_pdf_bytes)

    assert assessment.reason is ChangeReason.UNCHANGED
    assert not assessment.needs_extraction


def test_hash_change_flags_for_reextraction(sample_pdf_bytes: bytes) -> None:
    stored = _stored(sample_pdf_bytes, page_count=1)
    changed = _rerendered(sample_pdf_bytes)
    # Same page count, different bytes.
    assert fingerprint(changed).page_count == 1
    assert fingerprint(changed).content_sha256 != stored.content_sha256

    assessment = assess_document(stored, changed)

    assert assessment.reason is ChangeReason.HASH_CHANGED
    assert assessment.needs_extraction


def test_page_count_increase_flags_for_reextraction(sample_pdf_bytes: bytes) -> None:
    stored = _stored(sample_pdf_bytes, page_count=1)
    grown = _grown(sample_pdf_bytes)
    assert fingerprint(grown).page_count == 2

    assessment = assess_document(stored, grown)

    assert assessment.reason is ChangeReason.PAGE_COUNT_INCREASED
    assert assessment.needs_extraction


def test_first_sighting_is_new_document(sample_pdf_bytes: bytes) -> None:
    assessment = assess_document(None, sample_pdf_bytes)

    assert assessment.reason is ChangeReason.NEW_DOCUMENT
    assert assessment.needs_extraction


def test_poll_reads_previous_document_from_the_repository(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    """The poll compares against whatever the repository last stored for a member."""

    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)

    # No document yet: first poll is a new-document flag.
    first = poll_member(repo=repo, member_id=MEMBER_ID, new_pdf_bytes=sample_pdf_bytes)
    assert first.reason is ChangeReason.NEW_DOCUMENT

    # Store that document, then re-poll the identical bytes: no work.
    stored = store.store(
        sample_pdf_bytes,
        member_id=MEMBER_ID,
        fetched_at=FETCHED_AT,
        id_factory=id_factory,
    )
    repo.add_source_document(stored)
    again = poll_member(repo=repo, member_id=MEMBER_ID, new_pdf_bytes=sample_pdf_bytes)
    assert again.reason is ChangeReason.UNCHANGED
    assert not again.needs_extraction

    # A grown PDF re-polls as a page-count increase and flags the member.
    grown = poll_member(repo=repo, member_id=MEMBER_ID, new_pdf_bytes=_grown(sample_pdf_bytes))
    assert grown.reason is ChangeReason.PAGE_COUNT_INCREASED
    assert grown.needs_extraction


def test_poll_compares_against_the_most_recently_fetched_document(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    """A later fetch supersedes the earlier one as the comparison baseline."""

    repo = InMemoryRepository()
    store = DocumentStore(tmp_path)
    grown = _grown(sample_pdf_bytes)

    older = store.store(
        sample_pdf_bytes, member_id=MEMBER_ID, fetched_at=FETCHED_AT, id_factory=id_factory
    )
    newer = store.store(
        grown,
        member_id=MEMBER_ID,
        fetched_at=FETCHED_AT + timedelta(days=1),
        id_factory=id_factory,
    )
    repo.add_source_document(older)
    repo.add_source_document(newer)

    # Re-polling the grown (latest) bytes is unchanged, even though the older
    # one-page document is still on record.
    assessment = poll_member(repo=repo, member_id=MEMBER_ID, new_pdf_bytes=grown)
    assert assessment.reason is ChangeReason.UNCHANGED


def _stored(pdf_bytes: bytes, *, page_count: int) -> SourceDocument:
    """A stand-in stored SourceDocument carrying the fingerprint of ``pdf_bytes``."""

    fp = fingerprint(pdf_bytes)
    return SourceDocument(
        id=UUID(int=1),
        member_id=MEMBER_ID,
        content_sha256=fp.content_sha256,
        storage_path="/dev/null",
        page_count=page_count,
        fetched_at=FETCHED_AT,
    )

"""The source PDF is stored immutably and content-addressed."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from plain_sight.sources import DocumentStore

FETCHED_AT = datetime(2026, 7, 1, 9, 30, tzinfo=UTC)
MEMBER_ID = UUID(int=0xE)


def test_store_is_content_addressed_and_readable(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    store = DocumentStore(tmp_path)

    document = store.store(
        sample_pdf_bytes,
        member_id=MEMBER_ID,
        fetched_at=FETCHED_AT,
        source_url="https://example.test/register.pdf",
        id_factory=id_factory,
    )

    assert document.content_sha256 == hashlib.sha256(sample_pdf_bytes).hexdigest()
    assert document.page_count == 1
    assert Path(document.storage_path).name == f"{document.content_sha256}.pdf"
    assert store.read(document) == sample_pdf_bytes


def test_store_never_overwrites_existing_bytes(
    tmp_path: Path, sample_pdf_bytes: bytes, id_factory: Callable[[], UUID]
) -> None:
    store = DocumentStore(tmp_path)

    first = store.store(sample_pdf_bytes, member_id=MEMBER_ID, fetched_at=FETCHED_AT)
    # Re-storing identical bytes resolves to the same immutable file.
    second = store.store(sample_pdf_bytes, member_id=MEMBER_ID, fetched_at=FETCHED_AT)

    assert first.storage_path == second.storage_path
    assert Path(first.storage_path).read_bytes() == sample_pdf_bytes

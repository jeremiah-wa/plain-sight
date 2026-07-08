"""Immutable, content-addressed storage for source PDFs.

The original scan is the provenance anchor: every claim's provenance points at a
``SourceDocument`` id, and the bytes behind that id must never change even if the
government site later does. We enforce that by naming each file after the
SHA-256 of its content and never overwriting an existing file.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pypdf import PdfReader

from plain_sight.domain import SourceDocument


class DocumentStore:
    """Writes source PDFs into a content-addressed directory, write-once."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def store(
        self,
        content: bytes,
        *,
        member_id: UUID,
        fetched_at: datetime,
        source_url: str | None = None,
        jurisdiction: str = "AU:federal",
        id_factory: Callable[[], UUID] = uuid4,
    ) -> SourceDocument:
        """Persist ``content`` immutably and return its :class:`SourceDocument`.

        Storing the same bytes twice is idempotent at the file level: the path is
        derived from the content hash and an existing file is never rewritten, so
        the provenance anchor is stable.
        """

        content_sha256 = hashlib.sha256(content).hexdigest()
        page_count = len(PdfReader(io.BytesIO(content)).pages)

        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{content_sha256}.pdf"
        if not path.exists():
            path.write_bytes(content)

        return SourceDocument(
            id=id_factory(),
            member_id=member_id,
            content_sha256=content_sha256,
            storage_path=str(path),
            page_count=page_count,
            source_url=source_url,
            fetched_at=fetched_at,
            jurisdiction=jurisdiction,
        )

    def read(self, document: SourceDocument) -> bytes:
        """Read back the immutable bytes for ``document``."""

        return Path(document.storage_path).read_bytes()

"""Change detection: the cheap half of the monitoring loop.

The scheduled poll must notice when a member's register PDF has changed *without*
re-doing extraction when it has not. The signal is deliberately coarse and cheap:
a content hash plus a page count per member PDF (PRD "Change detection"). On a
re-poll a hash change, or a page-count increase, flags that member for
re-extraction; an unchanged document yields no work at all.

This module is the pure core of PRD seam 4,
``(previous document hash/state, new document) -> work-or-no-work``. Claim-level
diffing and supersession happen downstream, only for the members this stage flags;
the whole point is to never pay for extraction on the unchanged majority.
"""

from __future__ import annotations

import hashlib
import io
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from plain_sight.domain import SourceDocument


class DocumentFingerprint(BaseModel):
    """The cheap, stored signal used to tell whether a member PDF has changed.

    Exactly the two fields the PRD names: the SHA-256 of the PDF bytes and its
    page count. This is what gets persisted per member PDF and compared on the
    next poll; it is intentionally not the whole document.
    """

    model_config = ConfigDict(frozen=True)

    content_sha256: str = Field(min_length=64, max_length=64)
    page_count: int = Field(ge=1)


def fingerprint(pdf_bytes: bytes) -> DocumentFingerprint:
    """Compute a :class:`DocumentFingerprint` from raw PDF bytes."""

    return DocumentFingerprint(
        content_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        page_count=len(PdfReader(io.BytesIO(pdf_bytes)).pages),
    )


def fingerprint_of(document: SourceDocument) -> DocumentFingerprint:
    """The fingerprint already recorded on a stored :class:`SourceDocument`.

    The document store hashes and counts pages on ingest, so a previously stored
    document is compared without re-reading its bytes.
    """

    return DocumentFingerprint(
        content_sha256=document.content_sha256,
        page_count=document.page_count,
    )


class ChangeReason(StrEnum):
    """Why a poll did (or did not) produce re-extraction work."""

    #: No prior document for this member: first sight, so it must be extracted.
    NEW_DOCUMENT = "new_document"
    #: Byte-identical to what we last stored: nothing to do.
    UNCHANGED = "unchanged"
    #: More pages than before: an appended alteration/continuation page.
    PAGE_COUNT_INCREASED = "page_count_increased"
    #: Same page count but different bytes: an in-place revision.
    HASH_CHANGED = "hash_changed"


class ChangeAssessment(BaseModel):
    """The verdict of one poll: whether the member needs re-extraction, and why."""

    model_config = ConfigDict(frozen=True)

    reason: ChangeReason
    previous: DocumentFingerprint | None
    current: DocumentFingerprint

    @property
    def needs_extraction(self) -> bool:
        """``True`` for every reason except :attr:`ChangeReason.UNCHANGED`."""

        return self.reason is not ChangeReason.UNCHANGED


def assess_change(
    previous: DocumentFingerprint | None,
    current: DocumentFingerprint,
) -> ChangeAssessment:
    """Decide whether a freshly fetched document is worth re-extracting.

    The rules, in precedence order:

    * no ``previous`` -> :attr:`~ChangeReason.NEW_DOCUMENT` (work);
    * identical hash -> :attr:`~ChangeReason.UNCHANGED` (no work), the cheap
      common case a re-poll must not pay extraction for;
    * more pages than before -> :attr:`~ChangeReason.PAGE_COUNT_INCREASED` (work);
    * otherwise the bytes differ -> :attr:`~ChangeReason.HASH_CHANGED` (work).

    Page-count increase is checked before the generic hash change so a grown
    document is reported as such (its hash necessarily differs too), matching the
    PRD's "hash change *or* page-count increase" flag.
    """

    if previous is None:
        reason = ChangeReason.NEW_DOCUMENT
    elif previous.content_sha256 == current.content_sha256:
        reason = ChangeReason.UNCHANGED
    elif current.page_count > previous.page_count:
        reason = ChangeReason.PAGE_COUNT_INCREASED
    else:
        reason = ChangeReason.HASH_CHANGED

    return ChangeAssessment(reason=reason, previous=previous, current=current)


def assess_document(
    previous: SourceDocument | None,
    new_pdf_bytes: bytes,
) -> ChangeAssessment:
    """Assess freshly fetched PDF bytes against the previously stored document.

    Convenience over :func:`assess_change`: the previous document's fingerprint is
    read straight off its stored hash/page count, while the new bytes are hashed
    and page-counted here.
    """

    previous_fingerprint = None if previous is None else fingerprint_of(previous)
    return assess_change(previous_fingerprint, fingerprint(new_pdf_bytes))

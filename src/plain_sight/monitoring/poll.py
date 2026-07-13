"""Tie change detection to the system of record: previous document -> verdict.

This is the seam boundary the scheduled poll actually calls: given the member and
the freshly fetched PDF, it reads the previously stored document from the
repository and returns whether re-extraction is warranted. Only members whose
verdict :attr:`~plain_sight.monitoring.detect.ChangeAssessment.needs_extraction`
is ``True`` flow on to the (expensive) extraction and claim-level diffing.
"""

from __future__ import annotations

from uuid import UUID

from plain_sight.db.repository import Repository
from plain_sight.monitoring.detect import ChangeAssessment, assess_document


def poll_member(
    *,
    repo: Repository,
    member_id: UUID,
    new_pdf_bytes: bytes,
) -> ChangeAssessment:
    """Assess a member's freshly fetched PDF against their stored document.

    A member with no stored document yields ``NEW_DOCUMENT``; an unchanged re-poll
    yields ``UNCHANGED`` (no work); a hash change or page-count increase flags them
    for re-extraction.
    """

    previous = repo.latest_document_for_member(member_id)
    return assess_document(previous, new_pdf_bytes)

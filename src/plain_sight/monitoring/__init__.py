"""The monitoring loop: notice when a member's register changes, politely.

Two halves, one per PRD requirement:

* :mod:`plain_sight.monitoring.detect` - the cheap hash/page-count diff that
  turns ``(previous document, new document)`` into work-or-no-work (seam 4);
* :mod:`plain_sight.monitoring.fetch` + :mod:`plain_sight.monitoring.sources` -
  source-respectful fetching (robots, backoff, identifying bot, cache) over the
  authoritative aph.gov.au sources with OpenAustralia as an attributed fallback.
"""

from __future__ import annotations

from plain_sight.monitoring.detect import (
    ChangeAssessment,
    ChangeReason,
    DocumentFingerprint,
    assess_change,
    assess_document,
    fingerprint,
    fingerprint_of,
)
from plain_sight.monitoring.fetch import (
    DEFAULT_USER_AGENT,
    FetchError,
    FetchNotPermitted,
    FetchResponse,
    Opener,
    RespectfulFetcher,
)
from plain_sight.monitoring.poll import poll_member
from plain_sight.monitoring.sources import (
    APH_HOUSE,
    APH_SENATE,
    OPENAUSTRALIA,
    RegisterFetch,
    RegisterSource,
    SourceCandidate,
    fetch_register,
)

__all__ = [
    "APH_HOUSE",
    "APH_SENATE",
    "DEFAULT_USER_AGENT",
    "OPENAUSTRALIA",
    "ChangeAssessment",
    "ChangeReason",
    "DocumentFingerprint",
    "FetchError",
    "FetchNotPermitted",
    "FetchResponse",
    "Opener",
    "RegisterFetch",
    "RegisterSource",
    "RespectfulFetcher",
    "SourceCandidate",
    "assess_change",
    "assess_document",
    "fetch_register",
    "fingerprint",
    "fingerprint_of",
    "poll_member",
]

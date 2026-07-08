"""Seam 1: normalise extractor candidates into stored declaration events.

A pure function from a stored :class:`SourceDocument` plus an
:class:`ExtractionResult` to the counterparties and declaration events that
should be persisted. This is where per-claim provenance is attached and where a
declared counterparty becomes a first-class entity referenced by UUID rather
than an inlined string. Kept side-effect-free (ids come from an injected
factory) so it is asserted deterministically against fixtures.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    ExtractionResult,
    Provenance,
    SourceDocument,
    VerificationStatus,
)

_WHITESPACE = re.compile(r"\s+")


def normalise_counterparty(raw: str) -> str:
    """Produce a display label from a raw transcribed counterparty string.

    Conservative on purpose: trim, and collapse internal whitespace runs to a
    single space. It deliberately does not attempt to resolve or canonicalise the
    entity (that is a v2 concern with defamation risk); it only tidies the
    transcription so the same name declared twice reads consistently.
    """

    return _WHITESPACE.sub(" ", raw).strip()


def map_candidates(
    document: SourceDocument,
    result: ExtractionResult,
    *,
    ingested_at: datetime,
    id_factory: Callable[[], UUID] = uuid4,
) -> tuple[list[Counterparty], list[DeclarationEvent]]:
    """Map candidates to ``(counterparties, declaration_events)``.

    Counterparties are de-duplicated within the batch by their case-folded
    normalised label, so the same asset named on several claims resolves to one
    stable UUID. Every event references its counterparty by that UUID, carries a
    complete provenance pointer, and starts ``pending``.
    """

    counterparties_by_key: dict[str, Counterparty] = {}
    counterparties: list[Counterparty] = []
    events: list[DeclarationEvent] = []

    for candidate in result.candidates:
        label = normalise_counterparty(candidate.counterparty_raw)
        key = label.casefold()
        counterparty = counterparties_by_key.get(key)
        if counterparty is None:
            counterparty = Counterparty(
                id=id_factory(),
                raw_string=candidate.counterparty_raw,
                normalised_label=label,
                resolved=False,
            )
            counterparties_by_key[key] = counterparty
            counterparties.append(counterparty)

        provenance = Provenance(
            document_id=document.id,
            page=candidate.page,
            extraction_method=result.method,
            extraction_confidence=candidate.confidence,
            fetch_timestamp=document.fetched_at,
            bbox=candidate.bbox,
        )
        events.append(
            DeclarationEvent(
                id=id_factory(),
                member_id=document.member_id,
                counterparty_id=counterparty.id,
                category=candidate.category,
                description=candidate.description,
                valid_from=candidate.valid_from,
                valid_to=candidate.valid_to,
                provenance=provenance,
                verification_status=VerificationStatus.PENDING,
                ingested_at=ingested_at,
            )
        )

    return counterparties, events

"""An in-memory repository, for driving the pipeline deterministically in tests."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from plain_sight.db.repository import SimilarInterest, VerifiedClaim
from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    SourceDocument,
    VerificationStatus,
)


class InMemoryRepository:
    """A dict-backed :class:`~plain_sight.db.repository.Repository`."""

    def __init__(self) -> None:
        self._people: dict[UUID, Person] = {}
        self._documents: dict[UUID, SourceDocument] = {}
        self._counterparties: dict[UUID, Counterparty] = {}
        self._embeddings: dict[UUID, list[float]] = {}
        self._events: dict[UUID, DeclarationEvent] = {}

    def add_person(self, person: Person) -> None:
        self._people[person.id] = person

    def get_person_by_canonical_name(self, canonical_name: str) -> Person | None:
        for person in self._people.values():
            if person.canonical_name == canonical_name:
                return person
        return None

    def add_source_document(self, document: SourceDocument) -> None:
        self._documents[document.id] = document

    def add_counterparty(self, counterparty: Counterparty) -> None:
        self._counterparties[counterparty.id] = counterparty

    def add_declaration_event(self, event: DeclarationEvent) -> None:
        self._events[event.id] = event

    def verify_event(self, event_id: UUID, *, verified_by: str, verified_at: datetime) -> bool:
        event = self._events.get(event_id)
        if event is None or event.verification_status is not VerificationStatus.PENDING:
            return False
        self._events[event_id] = event.model_copy(
            update={
                "verification_status": VerificationStatus.VERIFIED,
                "verified_by": verified_by,
                "verified_at": verified_at,
            }
        )
        return True

    def verified_events_for_member(self, member_id: UUID) -> list[VerifiedClaim]:
        claims = [
            (event, self._counterparties[event.counterparty_id])
            for event in self._events.values()
            if event.member_id == member_id
            and event.verification_status is VerificationStatus.VERIFIED
        ]
        claims.sort(key=lambda claim: (claim[0].ingested_at, claim[0].id))
        return claims

    def set_counterparty_embedding(self, counterparty_id: UUID, embedding: Sequence[float]) -> None:
        self._embeddings[counterparty_id] = [float(value) for value in embedding]

    def similar_counterparty_interests(
        self,
        query_embedding: Sequence[float],
        *,
        category: InterestCategory | None = None,
        as_of: date | None = None,
    ) -> list[SimilarInterest]:
        query = [float(value) for value in query_embedding]
        results: list[SimilarInterest] = []
        for event in self._events.values():
            embedding = self._embeddings.get(event.counterparty_id)
            if embedding is None:
                continue
            if category is not None and event.category is not category:
                continue
            if as_of is not None and not _validity_contains(
                event.valid_from, event.valid_to, as_of
            ):
                continue
            distance = _cosine_distance(query, embedding)
            results.append((event, self._counterparties[event.counterparty_id], distance))
        results.sort(key=lambda item: (item[2], item[0].ingested_at, item[0].id))
        return results


def _validity_contains(valid_from: date | None, valid_to: date | None, as_of: date) -> bool:
    """Half-open ``[valid_from, valid_to)`` containment, mirroring ``daterange @>``."""

    if valid_from is not None and as_of < valid_from:
        return False
    if valid_to is not None and as_of >= valid_to:
        return False
    return True


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine distance ``1 - cos(a, b)``, matching pgvector's ``<=>`` operator."""

    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)

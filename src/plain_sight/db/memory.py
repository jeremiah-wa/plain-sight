"""An in-memory repository, for driving the pipeline deterministically in tests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from plain_sight.db.repository import PendingClaim, VerifiedClaim
from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
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

    def get_source_document(self, document_id: UUID) -> SourceDocument | None:
        return self._documents.get(document_id)

    def add_counterparty(self, counterparty: Counterparty) -> None:
        self._counterparties[counterparty.id] = counterparty

    def get_counterparty(self, counterparty_id: UUID) -> Counterparty | None:
        return self._counterparties.get(counterparty_id)

    def add_declaration_event(self, event: DeclarationEvent) -> None:
        self._events[event.id] = event

    def get_declaration_event(self, event_id: UUID) -> DeclarationEvent | None:
        return self._events.get(event_id)

    def supersede_event(self, original_event_id: UUID, successor: DeclarationEvent) -> bool:
        original = self._events.get(original_event_id)
        if (
            original is None
            or original.verification_status is not VerificationStatus.PENDING
            or original.superseded_by is not None
        ):
            return False
        self._events[successor.id] = successor
        self._events[original_event_id] = original.model_copy(
            update={"superseded_by": successor.id}
        )
        return True

    def pending_claims_for_member(self, member_id: UUID) -> list[PendingClaim]:
        claims = [
            (event, self._counterparties[event.counterparty_id], self._documents[doc_id])
            for event in self._events.values()
            if event.member_id == member_id
            and event.verification_status is VerificationStatus.PENDING
            and event.superseded_by is None
            if (doc_id := event.provenance.document_id) in self._documents
        ]
        claims.sort(key=lambda claim: (claim[0].ingested_at, claim[0].id))
        return claims

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

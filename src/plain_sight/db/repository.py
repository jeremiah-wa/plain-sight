"""The repository seam: what the application needs from the system of record.

Two implementations satisfy this Protocol: an in-memory one (used to drive the
walking skeleton deterministically in tests) and a ``psycopg`` v3 + raw SQL one
(the real Postgres system of record). Keeping the contract explicit is what lets
the verified-only display rule be asserted without a live database while the SQL
implementation is checked against the same contract under the ``postgres`` mark.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    SourceDocument,
)

#: A verified claim paired with the counterparty it was declared against.
VerifiedClaim = tuple[DeclarationEvent, Counterparty]

#: An interest (a declaration event) paired with the counterparty it names, as
#: returned by the bitemporal query views. Unlike :data:`VerifiedClaim` this is not
#: verification-filtered: the views reconstruct temporal state, and the events they
#: return are the current (non-superseded) versions of the record, whatever their
#: verification status.
MemberInterest = tuple[DeclarationEvent, Counterparty]

#: A declaration event, the counterparty it names, and that counterparty's cosine
#: distance from the query vector (smaller is nearer). The result unit of a
#: query-time similarity search. The distance is carried alongside so callers can
#: rank and threshold; it is a retrieval score, never an assertion of identity.
SimilarInterest = tuple[DeclarationEvent, Counterparty, float]


class Repository(Protocol):
    """Persistence operations for the walking skeleton."""

    def add_person(self, person: Person) -> None: ...

    def get_person_by_canonical_name(self, canonical_name: str) -> Person | None: ...

    def add_source_document(self, document: SourceDocument) -> None: ...

    def add_counterparty(self, counterparty: Counterparty) -> None: ...

    def add_declaration_event(self, event: DeclarationEvent) -> None: ...

    def verify_event(self, event_id: UUID, *, verified_by: str, verified_at: datetime) -> bool:
        """Transition a ``pending`` claim to ``verified``.

        Returns ``True`` if a pending event was transitioned, ``False`` if the
        event does not exist or was already verified.
        """
        ...

    def verified_events_for_member(self, member_id: UUID) -> list[VerifiedClaim]:
        """Return only ``verified`` claims for a member, oldest first.

        This is the single query behind the text display; the verified-only
        filter lives here so nothing ``pending`` can reach the reader.
        """
        ...

    def set_counterparty_embedding(self, counterparty_id: UUID, embedding: Sequence[float]) -> None:
        """Attach (or replace) a counterparty's retrieval embedding.

        The embedding is infrastructure for query-time similarity, not a domain
        fact: it lives beside the counterparty, never on the immutable claim, and
        setting it asserts nothing about the counterparty's legal identity.
        """
        ...

    def similar_counterparty_interests(
        self,
        query_embedding: Sequence[float],
        *,
        category: InterestCategory | None = None,
        as_of: date | None = None,
    ) -> list[SimilarInterest]:
        """Rank interests by how near their counterparty is to ``query_embedding``.

        Query-time semantic retrieval, no materialised clusters: every current
        (non-superseded) interest whose counterparty carries an embedding is
        scored by cosine distance and returned nearest-first. The optional
        ``category`` (structured) and ``as_of`` (temporal, valid-time) filters
        compose *with* the ranking in one pass, they do not bypass it. Results are
        cited records (each event keeps its provenance and its provisional
        counterparty); nothing is resolved to a legal identity.
        """
        ...

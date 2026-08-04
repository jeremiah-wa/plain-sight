"""The repository seam: what the application needs from the system of record.

Two implementations satisfy this Protocol: an in-memory one (used to drive the
walking skeleton deterministically in tests) and a ``psycopg`` v3 + raw SQL one
(the real Postgres system of record). Keeping the contract explicit is what lets
the verified-only display rule be asserted without a live database while the SQL
implementation is checked against the same contract under the ``postgres`` mark.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from plain_sight.domain import Counterparty, DeclarationEvent, Person, SourceDocument

#: A verified claim paired with the counterparty it was declared against.
VerifiedClaim = tuple[DeclarationEvent, Counterparty]

#: An interest (a declaration event) paired with the counterparty it names, as
#: returned by the bitemporal query views. Unlike :data:`VerifiedClaim` this is not
#: verification-filtered: the views reconstruct temporal state, and the events they
#: return are the current (non-superseded) versions of the record, whatever their
#: verification status.
MemberInterest = tuple[DeclarationEvent, Counterparty]

#: A pending claim as the verification UI needs it: the event, the counterparty it
#: names, and the source document whose scan is shown beside the extracted fields.
PendingClaim = tuple[DeclarationEvent, Counterparty, SourceDocument]


class Repository(Protocol):
    """Persistence operations for the walking skeleton."""

    def add_person(self, person: Person) -> None: ...

    def get_person_by_canonical_name(self, canonical_name: str) -> Person | None: ...

    def add_source_document(self, document: SourceDocument) -> None: ...

    def get_source_document(self, document_id: UUID) -> SourceDocument | None:
        """Return one source document by id, or ``None`` if absent.

        The verification UI needs it to render the scan a claim was read from,
        given only the claim's provenance ``document_id``.
        """
        ...

    def add_counterparty(self, counterparty: Counterparty) -> None: ...

    def get_counterparty(self, counterparty_id: UUID) -> Counterparty | None: ...

    def add_declaration_event(self, event: DeclarationEvent) -> None: ...

    def get_declaration_event(self, event_id: UUID) -> DeclarationEvent | None:
        """Return one declaration event by id, or ``None`` if absent."""
        ...

    def supersede_event(self, original_event_id: UUID, successor: DeclarationEvent) -> bool:
        """Append ``successor`` and mark the original superseded, atomically.

        The append-only correction path: the ``successor`` (a new event carrying
        the corrected values and its own verification metadata) is inserted, and
        the original is stamped ``superseded_by = successor.id``. The original is
        retained and never otherwise mutated. Returns ``True`` if the original was
        a current (non-superseded) ``pending`` claim, ``False`` otherwise.
        """
        ...

    def pending_claims_for_member(self, member_id: UUID) -> list[PendingClaim]:
        """Return the member's open (``pending``, non-superseded) claims, oldest first.

        This is the verification queue behind the UI: each claim is paired with its
        counterparty and the source document whose scan crop the operator checks it
        against. Settled (verified or superseded) claims are absent.
        """
        ...

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
